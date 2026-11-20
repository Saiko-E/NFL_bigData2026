"""Command line interface: inspect | run | reprocess | validate | sample | report | query."""
from __future__ import annotations

import argparse
import sys

import duckdb
import polars as pl

from .catalog import connect, query_df
from .config import Paths
from .pipeline import discover_tracking, run
from .quality import SchemaError
from .report import write_reports
from .schemas import SOURCES, TRACKING
from .validate import validate

pl.Config.set_tbl_rows(40).set_tbl_cols(20).set_tbl_width_chars(200).set_fmt_str_lengths(40)


def cmd_inspect(a, paths: Paths) -> int:
    """Compare actual CSV headers/types/row counts with the expected schemas."""
    con = duckdb.connect()
    items = [(n, paths.raw / f, s) for n, (f, s) in SOURCES.items()]
    files = discover_tracking(paths)
    if files:
        first = files[sorted(files)[0]]
        items.append((f"tracking ({first.name}, 1 of {len(files)} files)", first, TRACKING))
    rc = 0
    for name, path, schema in items:
        if not path.exists():
            print(f"[MISSING] {name}: {path}")
            rc = 1
            continue
        rel = f"read_csv('{path.as_posix()}', nullstr='NA', sample_size=-1)"
        desc = {r[0]: r[1] for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()}
        n = con.execute(f"SELECT count(*) FROM {rel}").fetchone()[0]
        miss = [c for c in schema if c not in desc]
        extra = [c for c in desc if c not in schema]
        print(f"\n== {name}: {n:,} rows, {len(desc)} columns, {path.stat().st_size / 1e6:.1f} MB")
        print(f"   missing required: {miss or 'none'} | extra: {extra or 'none'}")
        rc = rc or (1 if miss else 0)
        if a.verbose:
            for c, t in desc.items():
                print(f"   {c:26s} {t:22s} expected={schema[c] if c in schema else '-'}")
    if files:
        total = sum(f.stat().st_size for f in files.values()) / 1e6
        print(f"\ntracking files: {len(files)} ({total:.0f} MB total); ids {min(files)}..{max(files)}")
    return rc


def cmd_run(a, paths: Paths, force: bool = False, games: list[int] | None = None) -> int:
    try:
        res = run(paths, games=games or a.games, force=force or a.force, limit=a.limit,
                  aggregates=not a.skip_aggregates)
    except SchemaError as exc:
        print(f"SCHEMA ERROR: {exc}", file=sys.stderr)
        return 2
    return 0 if res.ok else 1


def cmd_reprocess(a, paths: Paths) -> int:
    a.limit, a.skip_aggregates = None, False
    return cmd_run(a, paths, force=True, games=a.game_ids)


def cmd_validate(a, paths: Paths) -> int:
    results = validate(paths)
    bad = 0
    for r in results:
        tag = "PASS" if r.passed else ("FAIL" if r.critical else "WARN")
        bad += (not r.passed) and r.critical
        print(f"[{tag}] {r.name}: {r.detail}")
    print(f"\n{sum(r.passed for r in results)}/{len(results)} checks passed; {bad} critical failure(s)")
    return 1 if bad else 0


def _df(con, sql: str) -> pl.DataFrame:
    return query_df(con, sql)


def cmd_sample(a, paths: Paths) -> int:
    con = connect(paths)
    if "tracking" not in {r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}:
        print("No processed tracking data. Run: etl run", file=sys.stderr)
        return 1
    if a.game and a.play:
        gid, pid = a.game, a.play
    else:
        where = f"WHERE gameId = {int(a.game)}" if a.game else ""
        rows = con.execute(f"SELECT gameId, playId FROM play_summary {where} "
                           "ORDER BY (qc_pass IS NOT TRUE), has_pressure DESC, gameId, playId LIMIT 1").fetchall()
        row = rows[0] if rows else None
        if not row:
            print("No matching play found.", file=sys.stderr)
            return 1
        gid, pid = row
    k = f"gameId = {int(gid)} AND playId = {int(pid)}"
    info = _df(con, f"SELECT gameId, playId, possessionTeam, defensiveTeam, quarter, down, yardsToGo, "
                       f"offenseFormation, pff_passCoverage, passResult, n_frames, snap_frame, "
                       f"pass_forward_frame, time_to_throw_s, n_pressure_rushers, qc_pass "
                       f"FROM play_summary WHERE {k}")
    if info.is_empty():
        print(f"Play {gid}/{pid} not found.", file=sys.stderr)
        return 1
    print("PLAY"); print(info.transpose(include_header=True, header_name="field", column_names=["value"]))
    print("\nEVENTS"); print(_df(con, f"SELECT frameId, event FROM events WHERE {k} ORDER BY 1"))
    print("\nKEY ENTITIES (QB, ball) every 10 frames, standardized coords (offense moves toward +x)")
    print(_df(con, f"""SELECT t.frameId, t.frames_since_snap, t.side, t.nflId, t.x, t.x_std, t.y_std, t.s,
        round(t.dist_to_qb, 2) AS dist_to_qb, round(t.nearest_opp_dist, 2) AS nearest_opp FROM tracking t
        JOIN play_meta m USING (gameId, playId)
        WHERE {k.replace('gameId', 't.gameId').replace('playId', 't.playId')} AND (t.side = 'ball' OR t.nflId = m.qb_nflId)
        AND (t.frameId - 1) % 10 = 0 ORDER BY t.side, t.frameId"""))
    print("\nPASS RUSH vs BLOCK (PFF), window metrics")
    print(_df(con, f"""SELECT nflId, team, pff_positionLinedUp AS pos, pff_role AS role,
        round(min_dist_to_qb_window, 2) AS min_dist_qb, round(max_speed_yps, 2) AS max_s, pff_hit AS hit,
        pff_hurry AS hurry, pff_sack AS sack, pff_nflIdBlockedPlayer AS blocked_id, pff_blockType AS blk
        FROM player_play WHERE {k} AND pff_role IN ('Pass Rush', 'Pass Block') ORDER BY pff_role, nflId"""))
    return 0


def cmd_report(a, paths: Paths) -> int:
    write_reports(paths)
    print(f"reports written to {paths.reports}")
    return 0


def cmd_query(a, paths: Paths) -> int:
    con = connect(paths)
    print(_df(con, a.sql))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nfl-etl", description="NFL tracking ETL (BDB 2023, weeks 1-8)")
    p.add_argument("--data-dir", help="override data directory (default: <project>/data or $NFL_DATA_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inspect", help="compare raw CSV schemas with the expected ones")
    s.add_argument("-v", "--verbose", action="store_true", help="list every column and type")
    s = sub.add_parser("run", help="run the ETL (skips games whose inputs are unchanged)")
    s.add_argument("--games", type=int, nargs="+", help="only these gameIds")
    s.add_argument("--limit", type=int, help="process only the first N games (smoke test)")
    s.add_argument("--force", action="store_true", help="reprocess even if unchanged")
    s.add_argument("--skip-aggregates", action="store_true")
    s = sub.add_parser("reprocess", help="force-reprocess selected games, then rebuild aggregates")
    s.add_argument("game_ids", type=int, nargs="+", metavar="GAME_ID")
    s = sub.add_parser("validate", help="validate processed outputs")
    s = sub.add_parser("sample", help="show one play (default: first QC-passing play with pressure)")
    s.add_argument("--game", type=int); s.add_argument("--play", type=int)
    sub.add_parser("report", help="regenerate the quality reports from existing manifests")
    s = sub.add_parser("query", help="run SQL over the views (tracking, plays, player_play, ...)")
    s.add_argument("sql")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    paths = Paths(__import__("pathlib").Path(a.data_dir)) if a.data_dir else Paths.default()
    fn = {"inspect": cmd_inspect, "run": cmd_run, "reprocess": cmd_reprocess, "validate": cmd_validate,
          "sample": cmd_sample, "report": cmd_report, "query": cmd_query}[a.cmd]
    return fn(a, paths)


if __name__ == "__main__":
    sys.exit(main())
