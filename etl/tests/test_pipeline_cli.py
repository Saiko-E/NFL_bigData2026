"""End-to-end tests on SYNTHETIC data: pipeline, idempotency, failure isolation, validation, CLI."""
import hashlib
import json

import duckdb
import pytest
from synthetic import G1, G2

from nfl_etl import cli
from nfl_etl.catalog import connect
from nfl_etl.pipeline import run
from nfl_etl.validate import validate


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def silent(_msg):
    pass


def test_end_to_end_outputs_are_queryable(paths):
    res = run(paths, progress=silent)
    assert res.ok and sorted(res.processed) == [G1, G2]
    files = sorted(paths.tracking.glob("week=*/part-*.parquet"))
    assert [f.parent.name for f in files] == ["week=1", "week=2"]
    con = connect(paths)
    assert con.execute("SELECT count(*) FROM tracking").fetchone()[0] == 3 * 12 * 23
    assert con.execute("SELECT count(DISTINCT week) FROM tracking").fetchone()[0] == 2  # hive column
    ps = con.execute("SELECT count(*), sum(n_pressure_rushers) FROM play_summary").fetchall()[0]
    assert ps == (3, 3)  # one PFF hurry per synthetic play
    pp = con.execute("SELECT count(*) FROM player_play WHERE pff_role = 'Pass Block' AND pff_nflIdBlockedPlayer IS NOT NULL").fetchone()[0]
    assert pp == 3 * 4
    # offense: AAA, BBB; defense: AAA, BBB, CCC
    assert con.execute("SELECT count(*) FROM team_summary").fetchone()[0] == 5
    assert (paths.reports / "quality_report.json").exists() and (paths.reports / "quality_report.md").exists()
    rep = json.loads((paths.reports / "quality_report.json").read_text())
    assert rep["totals"]["games_tracked"] == 2 and rep["totals"]["plays_tracked"] == 3
    assert rep["games"] == {"ok": 2, "failed": 0}
    assert rep["sources"]["tracking_rows_read"] == rep["sources"]["tracking_rows_written"] == 3 * 12 * 23


def test_second_run_skips_unchanged_and_changed_input_reprocesses(paths):
    run(paths, progress=silent)
    again = run(paths, progress=silent)
    assert again.processed == [] and sorted(again.skipped_unchanged) == [G1, G2]
    f = paths.raw_tracking / f"tracking_{G2}.csv"
    f.write_text(f.read_text().replace("2021-09-10T00:26:31Z", "2021-09-10T00:26:32Z", 1))
    third = run(paths, progress=silent)
    assert third.processed == [G2] and third.skipped_unchanged == [G1]


def test_outputs_are_deterministic(paths):
    run(paths, progress=silent)
    before = {p.name: sha(p) for p in paths.processed.rglob("*.parquet")}
    run(paths, force=True, progress=silent)
    after = {p.name: sha(p) for p in paths.processed.rglob("*.parquet")}
    assert before == after and len(before) > 8


def test_failed_game_is_recorded_and_does_not_stop_others(paths):
    f = paths.raw_tracking / f"tracking_{G2}.csv"
    f.write_text(f.read_text().replace('"dir",', '"dirX",', 1))
    res = run(paths, progress=silent)
    assert not res.ok and list(res.failed) == [G2] and res.processed == [G1]
    m = json.loads((paths.manifest / f"game_{G2}.json").read_text())
    assert m["status"] == "failed" and "dir" in m["error"]
    rep = json.loads((paths.reports / "quality_report.json").read_text())
    assert rep["games"] == {"ok": 1, "failed": 1} and str(G2) in rep["failed_games"]
    # a failed game is retried on the next run (not treated as unchanged)
    f.write_text(f.read_text().replace('"dirX",', '"dir",', 1))
    assert run(paths, progress=silent).processed == [G2]


def test_extra_and_unlisted_tracking_files_are_reported_not_fatal(paths):
    (paths.raw_tracking / "tracking_2021999999.csv").write_text("gameId\n1\n")
    res = run(paths, progress=silent)
    assert res.ok
    assert "tracking_2021999999.csv" in res.not_applicable


def test_reprocess_selected_game_only(paths):
    run(paths, progress=silent)
    t1 = paths.tracking / "week=1" / f"part-{G1}.parquet"
    t2 = paths.tracking / "week=2" / f"part-{G2}.parquet"
    m1, m2 = t1.stat().st_mtime_ns, t2.stat().st_mtime_ns
    res = run(paths, games=[G2], force=True, progress=silent)
    assert res.processed == [G2]
    assert t1.stat().st_mtime_ns == m1 and t2.stat().st_mtime_ns > m2


def test_unknown_requested_game_is_reported(paths):
    res = run(paths, games=[123], progress=silent)
    assert 123 in res.failed and not res.ok


def test_validation_passes_on_clean_synthetic_data(paths):
    run(paths, progress=silent)
    results = validate(paths)
    failed = [r for r in results if not r.passed and r.critical]
    assert not failed, failed
    assert len(results) >= 18


def test_validation_detects_corrupted_output(paths):
    run(paths, progress=silent)
    f = paths.tracking / "week=1" / f"part-{G1}.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * REPLACE (x_std + 5 AS x_std) FROM read_parquet('{f.as_posix()}')) "
                f"TO '{f.as_posix()}.new' (FORMAT PARQUET, COMPRESSION ZSTD)")
    f.with_name(f.name + ".new").replace(f)
    bad = {r.name for r in validate(paths) if not r.passed}
    assert "x_std_matches_direction" in bad


def test_validation_reports_missing_outputs(paths):
    results = validate(paths)
    assert results[0].name == "outputs_exist" and not results[0].passed


def test_cli_commands(paths, capsys):
    d = ["--data-dir", str(paths.data_dir)]
    assert cli.main(d + ["inspect"]) == 0
    assert cli.main(d + ["run"]) == 0
    assert cli.main(d + ["validate"]) == 0
    assert cli.main(d + ["sample"]) == 0
    assert cli.main(d + ["sample", "--game", str(G2), "--play", "1"]) == 0
    assert cli.main(d + ["sample", "--game", "5", "--play", "1"]) == 1
    assert cli.main(d + ["reprocess", str(G1)]) == 0
    assert cli.main(d + ["query", "select count(*) as n from plays"]) == 0
    out = capsys.readouterr().out
    assert "PLAY" in out and "Pass Rush" in out and "0 critical failure(s)" in out


def test_cli_schema_error_returns_2(paths):
    (paths.raw / "games.csv").write_text('"gameId"\n1\n')
    assert cli.main(["--data-dir", str(paths.data_dir), "run"]) == 2
    assert not paths.tracking.exists()  # nothing is written when the schema check fails
