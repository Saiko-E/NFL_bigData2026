"""Data-quality reports (JSON + Markdown) built from the per-game manifests and the Parquet outputs."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from .catalog import VIEWS, connect
from .config import PIPELINE_VERSION, Paths
from .io import write_json_atomic


def _load_manifests(paths: Paths) -> tuple[dict, list[dict]]:
    dims = {}
    dp = paths.manifest / "dims.json"
    if dp.exists():
        dims = json.loads(dp.read_text())
    games = []
    if paths.manifest.exists():
        for f in sorted(paths.manifest.glob("game_*.json")):
            games.append(json.loads(f.read_text()))
    return dims, games


def _table_counts(paths: Paths) -> dict[str, int]:
    con = connect(paths)
    out = {}
    for name in VIEWS:
        try:
            out[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        except Exception:  # noqa: BLE001 - view absent (dataset not built yet)
            continue
    return out


def _totals(paths: Paths) -> dict:
    con = connect(paths)
    t: dict = {}
    try:
        t["games_tracked"] = con.execute("SELECT count(DISTINCT gameId) FROM tracking").fetchone()[0]
        t["plays_tracked"] = con.execute("SELECT count(*) FROM play_meta").fetchone()[0]
        t["plays_qc_pass"] = con.execute("SELECT count(*) FROM play_meta WHERE qc_pass").fetchone()[0]
        t["players_tracked"] = con.execute(
            "SELECT count(DISTINCT nflId) FROM tracking WHERE nflId IS NOT NULL").fetchone()[0]
        t["frames_tracked"] = con.execute(
            "SELECT count(*) FROM (SELECT DISTINCT gameId, playId, frameId FROM tracking)").fetchone()[0]
    except Exception:  # noqa: BLE001
        pass
    try:
        t["plays_in_plays_csv"] = con.execute("SELECT count(*) FROM plays").fetchone()[0]
        t["players_in_players_csv"] = con.execute("SELECT count(*) FROM players").fetchone()[0]
        t["games_in_games_csv"] = con.execute("SELECT count(*) FROM games").fetchone()[0]
    except Exception:  # noqa: BLE001
        pass
    return t


def write_reports(paths: Paths, extra: dict | None = None) -> dict:
    dims, games = _load_manifests(paths)
    ok = [g for g in games if g.get("status") == "ok"]
    failed = [g for g in games if g.get("status") == "failed"]

    agg: dict[str, dict] = defaultdict(lambda: {"count": 0, "games": 0, "severity": "ok", "detail": ""})
    order = {"ok": 0, "info": 1, "warn": 2, "error": 3}
    for scope in [{"checks": dims.get("checks", [])}] + ok:
        for c in scope["checks"]:
            a = agg[c["name"]]
            a["count"] += c["count"]
            a["games"] += 1 if c["count"] else 0
            if order[c["severity"]] > order[a["severity"]]:
                a["severity"] = c["severity"]
            if c["count"] and not a["detail"]:
                a["detail"] = c["detail"]
    checks = {k: v for k, v in sorted(agg.items())}

    excl: dict[str, dict] = defaultdict(lambda: {"n_rows": 0, "games": 0, "reason": "", "action": ""})
    for scope in [{"exclusions": dims.get("exclusions", [])}] + ok:
        for e in scope["exclusions"]:
            x = excl[f'{e["source"]}.{e["rule"]}']
            x["n_rows"] += e["n_rows"]
            x["games"] += 1
            x["reason"], x["action"] = e["reason"], e["action"]

    sources = {"tracking_rows_read": sum(g.get("rows_in", 0) for g in ok),
               "tracking_rows_written": sum(g.get("rows_out", 0) for g in ok)}
    for c in dims.get("checks", []):
        if c["name"].endswith(".rows_read"):
            sources[c["name"].replace(".rows_read", "") + "_rows_read"] = c["total"]

    report = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_version": PIPELINE_VERSION,
        "totals": _totals(paths), "sources": sources, "output_tables": _table_counts(paths),
        "games": {"ok": len(ok), "failed": len(failed)},
        "failed_games": {g["gameId"]: g.get("error", "") for g in failed},
        "run": extra or {}, "checks": checks, "exclusions": dict(excl),
    }
    write_json_atomic(report, paths.reports / "quality_report.json")
    # Full exclusion details (with example keys) live in separate files so the report stays small.
    detail = {"dims": dims.get("exclusions", []),
              "games": {g["gameId"]: g["exclusions"] for g in ok if g["exclusions"]}}
    write_json_atomic(detail, paths.reports / "exclusions_detail.json")
    (paths.reports / "quality_report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(r: dict) -> str:
    t, run = r["totals"], r["run"]
    L = [f"# Data quality report (pipeline v{r['pipeline_version']})", "",
         f"Generated: {r['generated_utc']}", "", "## Totals", ""]
    for k, v in t.items():
        L.append(f"- {k}: {v:,}")
    L += ["", "## Records per source", ""] + [f"- {k}: {v:,}" for k, v in r["sources"].items()]
    L += ["", "## Records per output table", ""] + [f"- {k}: {v:,}" for k, v in r["output_tables"].items()]
    L += ["", f"## Games: {r['games']['ok']} ok, {r['games']['failed']} failed", ""]
    for gid, err in r["failed_games"].items():
        L.append(f"- FAILED {gid}: {err}")
    for k, v in run.get("failed", {}).items():
        L.append(f"- FAILED (this run) {k}: {v}")
    for k, v in run.get("not_applicable", {}).items():
        L.append(f"- SKIPPED {k}: {v}")
    L += ["", "## Checks with findings", "", "| check | severity | rows/items | games affected | note |",
          "|---|---|---:|---:|---|"]
    for name, c in r["checks"].items():
        if c["count"] and c["severity"] != "ok":
            L.append(f"| {name} | {c['severity']} | {c['count']:,} | {c['games']} | {c['detail'][:90]} |")
    passed = sum(1 for c in r["checks"].values() if not c["count"])
    L += ["", f"Checks with no findings: {passed} of {len(r['checks'])}.", "",
          "## Exclusions (rows removed from outputs)", ""]
    if not r["exclusions"]:
        L.append("None. No rows were dropped from any source.")
    for name, e in r["exclusions"].items():
        L.append(f"- {name}: {e['n_rows']:,} rows in {e['games']} game(s) ({e['action']}): {e['reason']}")
    L += ["", "Details with example keys: `exclusions_detail.json`. Rows flagged in `qc_flags` are "
          "kept in the output and are not listed as exclusions.", ""]
    return "\n".join(L)
