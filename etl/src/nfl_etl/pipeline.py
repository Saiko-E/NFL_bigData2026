"""ETL orchestration: dims -> per-game tracking -> aggregates -> reports.

Idempotent: each game has a manifest keyed on (input CSV hash, dims hash, pipeline version).
A game is skipped when its manifest matches and outputs exist, unless force=True.
A failure in one game is recorded and does not stop the run.
"""
from __future__ import annotations

import hashlib
import re
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from .aggregates import build_aggregates
from .config import PIPELINE_VERSION, Paths
from .dims import Dims, build_dims
from .io import sha256_file, write_json_atomic, write_parquet_atomic
from .quality import QualityLog, SchemaError
from .report import write_reports
from .schemas import SOURCES
from .tracking import read_game_csv, transform_game

TRACKING_RE = re.compile(r"^tracking_(\d+)\.csv$")


@dataclass
class RunResult:
    processed: list[int] = field(default_factory=list)
    skipped_unchanged: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)
    not_applicable: dict[str, str] = field(default_factory=dict)  # file/game -> reason
    seconds: float = 0.0
    aggregates: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed


def discover_tracking(paths: Paths) -> dict[int, Path]:
    files: dict[int, Path] = {}
    if paths.raw_tracking.exists():
        for f in sorted(paths.raw_tracking.iterdir()):
            m = TRACKING_RE.match(f.name)
            if m:
                files[int(m.group(1))] = f
    return files


def dims_fingerprint(paths: Paths) -> str:
    h = hashlib.sha256()
    for fname, _ in SOURCES.values():
        h.update(sha256_file(paths.raw / fname).encode())
    return h.hexdigest()


def manifest_path(paths: Paths, game_id: int) -> Path:
    return paths.manifest / f"game_{game_id}.json"


def output_paths(paths: Paths, game_id: int, week: int) -> tuple[Path, Path]:
    return (paths.tracking / f"week={week}" / f"part-{game_id}.parquet",
            paths.processed / "play_meta" / f"{game_id}.parquet")


def _is_current(paths: Paths, game_id: int, week: int, key: dict) -> bool:
    mp = manifest_path(paths, game_id)
    if not mp.exists():
        return False
    import json
    try:
        m = json.loads(mp.read_text())
    except (OSError, ValueError):
        return False
    t, pm = output_paths(paths, game_id, week)
    return m.get("status") == "ok" and m.get("key") == key and t.exists() and pm.exists()


def process_game(paths: Paths, dims: Dims, game_id: int, csv_path: Path, key: dict) -> dict:
    """Transform one game and write its outputs + manifest. Raises on unrecoverable errors."""
    t0 = time.time()
    log = QualityLog(f"game:{game_id}")
    week = int(dims.games.filter(pl.col("gameId") == game_id)["week"][0])
    raw = read_game_csv(csv_path, log)
    plays = dims.plays.filter(pl.col("gameId") == game_id)
    pff = dims.pff.filter(pl.col("gameId") == game_id)
    out, meta = transform_game(raw, game_id, plays, pff, set(dims.players["nflId"].to_list()), log)
    tpath, mpath = output_paths(paths, game_id, week)
    write_parquet_atomic(out, tpath)
    write_parquet_atomic(meta, mpath)
    plays_no_tracking = plays.join(meta.select("playId"), on="playId", how="anti")
    log.exclude("plays", "play_without_tracking", "play in plays.csv has no tracking rows in this game",
                plays_no_tracking, ["gameId", "playId"], action="not_in_tracking_output")
    manifest = {
        "gameId": game_id, "week": week, "status": "ok", "key": key, "version": PIPELINE_VERSION,
        "rows_in": raw.height, "rows_out": out.height, "plays_out": meta.height,
        "plays_in_plays_csv": plays.height, "seconds": round(time.time() - t0, 2),
        "checks": log.checks, "exclusions": log.exclusions,
    }
    write_json_atomic(manifest, manifest_path(paths, game_id))
    return manifest


def run(paths: Paths | None = None, games: list[int] | None = None, force: bool = False,
        limit: int | None = None, aggregates: bool = True, progress=print) -> RunResult:
    paths = paths or Paths.default()
    res = RunResult()
    t0 = time.time()
    dims = build_dims(paths)  # raises SchemaError on structural problems: nothing is written after that
    write_json_atomic({"checks": dims.log.checks, "exclusions": dims.log.exclusions,
                       "version": PIPELINE_VERSION}, paths.manifest / "dims.json")
    progress(f"dims: games={dims.games.height} plays={dims.plays.height} players={dims.players.height} "
             f"pff={dims.pff.height}")

    files = discover_tracking(paths)
    known = set(dims.games["gameId"].to_list())
    for gid in sorted(set(files) - known):
        res.not_applicable[f"tracking_{gid}.csv"] = "game not in games.csv; skipped"
    for gid in sorted(known - set(files)):
        res.not_applicable[f"game {gid}"] = "no tracking file in data/raw/tracking"
    todo = sorted(set(files) & known)
    if games:
        unknown = sorted(set(games) - set(todo))
        for gid in unknown:
            res.failed[gid] = "requested game has no tracking file or is not in games.csv"
        todo = [g for g in todo if g in set(games)]
    if limit:
        todo = todo[:limit]

    key_base = {"dims": dims_fingerprint(paths), "version": PIPELINE_VERSION}
    week_of = dict(zip(dims.games["gameId"].to_list(), dims.games["week"].to_list()))
    for i, gid in enumerate(todo, 1):
        key = {**key_base, "csv": sha256_file(files[gid])}
        if not force and _is_current(paths, gid, week_of[gid], key):
            res.skipped_unchanged.append(gid)
            continue
        try:
            m = process_game(paths, dims, gid, files[gid], key)
            res.processed.append(gid)
            progress(f"[{i}/{len(todo)}] game {gid}: {m['rows_out']:,} rows, {m['plays_out']} plays, "
                     f"{m['seconds']}s")
        except Exception as exc:  # noqa: BLE001 - record and continue with the next game
            msg = f"{type(exc).__name__}: {exc}"
            res.failed[gid] = msg
            write_json_atomic({"gameId": gid, "status": "failed", "error": msg, "key": key,
                               "trace": traceback.format_exc(limit=5), "checks": [], "exclusions": []},
                              manifest_path(paths, gid))
            progress(f"[{i}/{len(todo)}] game {gid}: FAILED {msg}")
    if res.skipped_unchanged:
        progress(f"skipped {len(res.skipped_unchanged)} unchanged games (use --force to rebuild)")

    if aggregates and (paths.tracking.exists() and any(paths.tracking.glob("*/*.parquet"))):
        res.aggregates = build_aggregates(paths)
        progress("aggregates: " + ", ".join(f"{k}={v:,}" for k, v in res.aggregates.items()))
    res.seconds = round(time.time() - t0, 1)
    extra = {"not_applicable": res.not_applicable, "failed": res.failed,
             "run_seconds": res.seconds, "processed_this_run": res.processed,
             "skipped_unchanged": len(res.skipped_unchanged)}
    write_reports(paths, extra)
    progress(f"done in {res.seconds}s | processed={len(res.processed)} unchanged={len(res.skipped_unchanged)} "
             f"failed={len(res.failed)} | reports: {paths.reports}")
    return res


__all__ = ["run", "RunResult", "SchemaError", "discover_tracking"]
