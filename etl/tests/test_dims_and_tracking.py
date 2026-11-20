"""Unit tests on SYNTHETIC data (see synthetic.py): dimension building and tracking transform."""
import polars as pl
import pytest
from synthetic import G1, G2

from nfl_etl.dims import build_dims
from nfl_etl.io import read_csv_typed
from nfl_etl.quality import QualityLog, SchemaError
from nfl_etl.schemas import PLAYS, TRACKING
from nfl_etl.tracking import (FLAG_ACCEL, FLAG_DIS, FLAG_POSITION, FLAG_SPEED, FLAG_UNKNOWN_SIDE,
                              read_game_csv, transform_game)


def check(log: QualityLog, name: str) -> dict:
    return next(c for c in log.checks if c["name"] == name)


def run_game(paths, dims, gid, raw=None):
    log = QualityLog(f"game:{gid}")
    raw = raw if raw is not None else read_game_csv(paths.raw_tracking / f"tracking_{gid}.csv", log)
    out, meta = transform_game(raw, gid, dims.plays.filter(pl.col("gameId") == gid),
                               dims.pff.filter(pl.col("gameId") == gid),
                               set(dims.players["nflId"].to_list()), log)
    return out, meta, log, raw


# ---------------- dims ----------------
def test_dims_basic_parsing(dims):
    assert dims.games.height == 2 and dims.plays.height == 3 and dims.pff.height == 66
    p = dims.players
    assert p.filter(pl.col("nflId") == 1)["heightInches"][0] == 74  # "6-2"
    assert p.filter(pl.col("nflId") == 1)["positionGroup"][0] == "QB"
    assert p.filter(pl.col("nflId") == 7)["positionGroup"][0] == "OL"  # T
    births = p["birthDate"]
    assert births.null_count() == 0  # both YYYY-MM-DD and MM/DD/YYYY parsed
    assert dims.plays.filter(pl.col("playId") == 2).filter(pl.col("gameId") == G1)["isSack"][0] is True
    assert dims.pff["pff_hurry"].dtype == pl.Boolean
    assert not [c for c in dims.log.checks if c["severity"] == "error" and c["count"]]


def test_missing_required_column_raises(paths):
    p = paths.raw / "plays.csv"
    txt = p.read_text().replace('"passResult",', '"passResultX",', 1)
    p.write_text(txt)
    with pytest.raises(SchemaError, match="passResult"):
        build_dims(paths, write=False)


def test_duplicate_and_orphan_keys_are_detected(paths):
    pff = paths.raw / "pffScoutingData.csv"
    lines = pff.read_text().splitlines()
    lines.append(lines[1])  # exact duplicate key
    pff.write_text("\n".join(lines) + "\n")
    d = build_dims(paths, write=False)
    c = check(d.log, "pff.duplicate_keys")
    assert c["count"] == 1 and c["severity"] == "error"
    assert d.pff.height == 66  # deduplicated


def test_type_coercion_failures_are_logged(paths):
    p = paths.raw / "plays.csv"
    p.write_text(p.read_text().replace('"13:33",0,0', '"13:33",zero,0', 1))
    log = QualityLog("t")
    df = read_csv_typed(p, PLAYS, log, "plays")
    assert df["preSnapHomeScore"].null_count() == 1
    assert check(log, "plays.type_coercion.preSnapHomeScore")["count"] == 1


# ---------------- tracking ----------------
def test_output_structure_and_sorting(paths, dims):
    out, meta, log, raw = run_game(paths, dims, G1)
    assert out.height == raw.height == 2 * 12 * 23
    keys = out.select("playId", "frameId")
    assert keys.equals(keys.sort("playId", "frameId"))
    assert meta.height == 2 and meta["qc_pass"].all()
    assert set(out["side"].unique()) == {"ball", "offense", "defense"}


def test_football_rows_keep_null_nflid_and_ball_side(paths, dims):
    out, *_ = run_game(paths, dims, G1)
    ball = out.filter(pl.col("side") == "ball")
    assert ball.height == 2 * 12 and ball["nflId"].null_count() == ball.height
    assert out.filter(pl.col("side") != "ball")["nflId"].null_count() == 0


def test_direction_normalization_and_raw_preserved(paths, dims):
    out, meta, log, raw = run_game(paths, dims, G1)
    left = out.filter(pl.col("playId") == 2)  # direction left
    right = out.filter(pl.col("playId") == 1)
    assert (left["x_std"] - (120.0 - left["x"])).abs().max() < 1e-9
    assert (left["y_std"] - (53.3 - left["y"])).abs().max() < 1e-9
    assert (right["x_std"] - right["x"]).abs().max() < 1e-9
    # raw columns unchanged versus the source file
    src = raw.sort("playId", "frameId", "nflId", nulls_last=True)
    assert out["x"].to_list() == src["x"].to_list() and out["dir"].to_list() == src["dir"].to_list()
    # angles flip by 180 for the left play
    qb_left = left.filter(pl.col("frames_since_snap") == 5, pl.col("nflId") == 23)
    assert qb_left["dir"][0] == 90.0 and qb_left["dir_std"][0] == 270.0


def test_qb_behind_line_at_snap_for_both_directions(paths, dims):
    out, meta, *_ = run_game(paths, dims, G1)
    qbs = meta.select("playId", "qb_nflId")
    at_snap = out.filter(pl.col("frames_since_snap") == 0).join(qbs, on="playId").filter(
        pl.col("nflId") == pl.col("qb_nflId"))
    assert at_snap.height == 2
    assert (at_snap["x_rel_los"] < 0).all()
    assert at_snap["x_rel_los"].to_list() == pytest.approx([-5.0, -5.0], abs=1e-6)


def test_snap_frame_prefers_ball_snap_over_autoevent(paths, dims):
    out, meta, *_ = run_game(paths, dims, G1)
    assert meta["snap_frame"].unique().to_list() == [3]
    assert meta["snap_frame_event"].unique().to_list() == ["ball_snap"]
    assert meta["pass_forward_frame"].unique().to_list() == [8]
    assert meta["time_to_throw_s"].unique().to_list() == [0.5]
    assert out.filter(pl.col("frameId") == 3)["frames_since_snap"].unique().to_list() == [0]


def test_distances_to_qb_and_ball_and_opponents(paths, dims):
    out, *_ = run_game(paths, dims, G1)
    f = out.filter(pl.col("playId") == 1, pl.col("frameId") == 1)
    qb = f.filter(pl.col("nflId") == 1)
    assert qb["dist_to_qb"][0] is None  # QB distance to self is not defined
    rb = f.filter(pl.col("nflId") == 2)
    expected = ((rb["x"][0] - qb["x"][0]) ** 2 + (rb["y"][0] - qb["y"][0]) ** 2) ** 0.5
    assert rb["dist_to_qb"][0] == pytest.approx(expected, rel=1e-5)
    assert f.filter(pl.col("side") == "ball")["dist_to_ball"][0] is None
    off, dfn = f.filter(pl.col("side") == "offense"), f.filter(pl.col("side") == "defense")
    best = {}
    for a in off.iter_rows(named=True):
        best[a["nflId"]] = min(((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
                               for b in dfn.iter_rows(named=True))
    got = dict(zip(off["nflId"].to_list(), off["nearest_opp_dist"].to_list()))
    for k, v in best.items():
        assert got[k] == pytest.approx(v, rel=1e-5)
    assert f.filter(pl.col("side") == "ball")["nearest_opp_dist"][0] is None


def test_out_of_range_values_are_flagged_not_dropped(paths, dims):
    log = QualityLog("t")
    raw = read_game_csv(paths.raw_tracking / f"tracking_{G1}.csv", log)
    idx = raw.with_row_index("i").filter(
        (pl.col("playId") == 1) & (pl.col("frameId") == 5) & (pl.col("nflId") == 3))["i"][0]
    raw = raw.with_row_index("i").with_columns(
        pl.when(pl.col("i") == idx).then(40.0).otherwise(pl.col("s")).alias("s"),
        pl.when(pl.col("i") == idx).then(99.0).otherwise(pl.col("a")).alias("a"),
        pl.when(pl.col("i") == idx).then(9.0).otherwise(pl.col("dis")).alias("dis"),
        pl.when(pl.col("i") == idx).then(200.0).otherwise(pl.col("x")).alias("x"),
    ).drop("i")
    out, meta, log, _ = run_game(paths, dims, G1, raw=raw)
    assert out.height == raw.height  # nothing dropped
    flag = out.filter(pl.col("playId") == 1, pl.col("frameId") == 5, pl.col("nflId") == 3)["qc_flags"][0]
    assert flag & FLAG_SPEED and flag & FLAG_ACCEL and flag & FLAG_DIS and flag & FLAG_POSITION
    assert meta.filter(pl.col("playId") == 1)["qc_pass"][0] is False
    assert check(log, "tracking.flag.speed_out_of_range")["count"] == 1


def test_duplicates_and_orphans_are_excluded_with_log(paths, dims):
    log0 = QualityLog("t")
    raw = read_game_csv(paths.raw_tracking / f"tracking_{G1}.csv", log0)
    extra = raw.head(1)  # duplicate key
    orphan = raw.head(2).with_columns(pl.lit(777, dtype=pl.Int64).alias("playId"))  # play not in plays.csv
    foreign = raw.head(1).with_columns(pl.lit(G2, dtype=pl.Int64).alias("gameId"))  # other game's id in this file
    out, meta, log, _ = run_game(paths, dims, G1, raw=pl.concat([raw, extra, orphan, foreign]))
    assert out.height == 2 * 12 * 23
    assert check(log, "duplicate_key")["count"] == 1
    assert check(log, "play_not_in_plays_csv")["count"] == 2
    assert check(log, "wrong_gameId")["count"] == 1
    assert {e["rule"] for e in log.exclusions} >= {"duplicate_key", "play_not_in_plays_csv", "wrong_gameId"}
    assert all(e["keys"] for e in log.exclusions)


def test_unknown_team_is_flagged(paths, dims):
    log = QualityLog("t")
    raw = read_game_csv(paths.raw_tracking / f"tracking_{G1}.csv", log).with_row_index("i")
    raw = raw.with_columns(pl.when(pl.col("i") == 5).then(pl.lit("ZZZ")).otherwise(pl.col("team")).alias("team")).drop("i")
    out, *_ = run_game(paths, dims, G1, raw=raw)
    assert (out["qc_flags"] & FLAG_UNKNOWN_SIDE).sum() > 0
    assert out.height == raw.height


def test_tracking_schema_error_on_missing_column(paths):
    p = paths.raw_tracking / f"tracking_{G1}.csv"
    p.write_text(p.read_text().replace('"dir",', '"dirX",', 1))
    with pytest.raises(SchemaError):
        read_csv_typed(p, TRACKING, QualityLog("t"), "tracking")
