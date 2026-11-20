"""Per-game tracking transform: validation, normalization, derived columns, play-level QC.

Everything is computed within one game at a time (~90k rows), so memory stays small.
Proximity joins are bounded to a single (play, frame) and to offense x defense (121 pairs).
"""
from __future__ import annotations

import polars as pl

from .config import (ENTITIES_PER_FRAME, FIELD_LENGTH, FIELD_WIDTH, LIMITS, LOS_TOLERANCE_YDS,
                     PLAYERS_PER_FRAME, SNAP_EVENTS, X_RANGE, Y_RANGE)
from .io import read_csv_typed
from .quality import QualityLog
from .schemas import TRACKING

# Bit flags stored in the `qc_flags` column. Rows are flagged, never dropped, for these.
# play_meta.qc_pass uses player rows only; ball flags are counted separately (n_ball_flagged_rows)
# because ball `dis` is a plain position difference and shows jumps up to ~10 yd/frame.
FLAG_POSITION = 1  # x or y outside the field (with tolerance)
FLAG_SPEED = 2
FLAG_ACCEL = 4
FLAG_DIS = 8
FLAG_MISSING_CORE = 16  # null x/y/s/a/dis on a player row
FLAG_UNKNOWN_SIDE = 32  # team is neither possession nor defensive team of the play
FLAG_BAD_DIRECTION = 64  # playDirection not in {left,right}: standardized columns are null
FLAG_NAMES = {FLAG_POSITION: "position_out_of_range", FLAG_SPEED: "speed_out_of_range",
              FLAG_ACCEL: "accel_out_of_range", FLAG_DIS: "dis_out_of_range",
              FLAG_MISSING_CORE: "missing_core_value", FLAG_UNKNOWN_SIDE: "unknown_side",
              FLAG_BAD_DIRECTION: "bad_direction"}

PASS_FORWARD_EVENTS = ("pass_forward", "autoevent_passforward")
OUT_COLS = [
    "gameId", "playId", "frameId", "nflId", "side", "team", "jerseyNumber", "time", "playDirection",
    "x", "y", "s", "a", "dis", "o", "dir", "event",
    "x_std", "y_std", "o_std", "dir_std", "vx_std", "vy_std", "x_rel_los", "frames_since_snap",
    "dist_to_ball", "dist_to_qb", "nearest_opp_dist", "nearest_opp_id", "qc_flags",
]


def read_game_csv(path, log: QualityLog) -> pl.DataFrame:
    return read_csv_typed(path, TRACKING, log, "tracking")


def _first_frame(df: pl.DataFrame, events: tuple[str, ...], name: str) -> pl.DataFrame:
    """First frame per play where an event in `events` occurs; earlier tuple entries take priority."""
    parts = []
    for rank, ev in enumerate(events):
        parts.append(df.filter(pl.col("event") == ev).group_by("playId")
                     .agg(pl.col("frameId").min().alias(name), pl.lit(ev).alias(f"{name}_event"),
                          pl.lit(rank).alias("_rank")))
    if not parts:
        return pl.DataFrame(schema={"playId": pl.Int64, name: pl.Int64, f"{name}_event": pl.String})
    allp = pl.concat(parts)
    return (allp.sort("playId", "_rank").unique(subset="playId", keep="first", maintain_order=True)
            .drop("_rank"))


def _clean_rows(raw: pl.DataFrame, game_id: int, plays: pl.DataFrame, log: QualityLog) -> pl.DataFrame:
    """Row-level exclusions. Every dropped row is logged with its reason."""
    log.check("tracking.rows_read", 0, severity="info", detail=f"{raw.height} rows", total=raw.height)
    keycols = ["gameId", "playId", "frameId", "nflId"]
    df = raw
    bad = df.filter(pl.col("gameId") != game_id)
    log.exclude("tracking", "wrong_gameId", "row gameId differs from the file's game", bad, keycols)
    df = df.filter(pl.col("gameId") == game_id)

    bad = df.filter(pl.col("playId").is_null() | pl.col("frameId").is_null() | (pl.col("frameId") < 1))
    log.exclude("tracking", "invalid_play_or_frame", "null playId/frameId or frameId < 1", bad, keycols)
    df = df.filter(pl.col("playId").is_not_null() & pl.col("frameId").is_not_null() & (pl.col("frameId") >= 1))

    is_ball = (pl.col("team") == "football").fill_null(False)
    bad = df.filter(pl.col("nflId").is_null() & ~is_ball)
    log.exclude("tracking", "player_without_nflId", "non-football row with null nflId (unidentifiable)",
                bad, keycols)
    df = df.filter(pl.col("nflId").is_not_null() | is_ball)
    log.check("tracking.football_row_with_nflId", df.filter(is_ball & pl.col("nflId").is_not_null()).height,
              detail="kept as-is; treated as ball by team == 'football'")

    df = df.with_row_index("_i")
    first = df.unique(subset=["playId", "frameId", "nflId"], keep="first", maintain_order=True)
    dup = df.join(first.select("_i"), on="_i", how="anti")
    log.exclude("tracking", "duplicate_key", "repeated (playId, frameId, nflId); first occurrence kept",
                dup, keycols)
    df = first.drop("_i")

    orphan = df.join(plays.select("playId"), on="playId", how="anti")
    log.exclude("tracking", "play_not_in_plays_csv", "playId has no row in plays.csv", orphan, keycols)
    return df.join(plays.select("playId"), on="playId", how="semi")


def _proximity(df: pl.DataFrame) -> pl.DataFrame:
    """Nearest opposing player for each offense/defense player in each frame (offense x defense only)."""
    p = df.filter(pl.col("side").is_in(["offense", "defense"]) & pl.col("x").is_not_null()
                  & pl.col("y").is_not_null()).select("playId", "frameId", "nflId", "side", "x", "y")
    off = p.filter(pl.col("side") == "offense").drop("side").rename(
        {"nflId": "a_id", "x": "ax", "y": "ay"})
    dfn = p.filter(pl.col("side") == "defense").drop("side").rename(
        {"nflId": "b_id", "x": "bx", "y": "by"})
    pairs = off.join(dfn, on=["playId", "frameId"]).with_columns(
        ((pl.col("ax") - pl.col("bx")) ** 2 + (pl.col("ay") - pl.col("by")) ** 2).sqrt().alias("d"))

    def nearest(key: str, other: str) -> pl.DataFrame:
        return (pairs.sort("playId", "frameId", key, "d", other)
                .unique(subset=["playId", "frameId", key], keep="first", maintain_order=True)
                .select("playId", "frameId", pl.col(key).alias("nflId"),
                        pl.col("d").alias("nearest_opp_dist"), pl.col(other).alias("nearest_opp_id")))

    return pl.concat([nearest("a_id", "b_id"), nearest("b_id", "a_id")])


def transform_game(raw: pl.DataFrame, game_id: int, plays: pl.DataFrame, pff: pl.DataFrame,
                   player_ids: set[int], log: QualityLog) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (tracking_out, play_meta) for one game."""
    play_cols = plays.select("playId", "possessionTeam", "defensiveTeam", "absoluteYardlineNumber")
    df = _clean_rows(raw, game_id, play_cols, log)
    if df.is_empty():
        raise ValueError("no valid tracking rows left after cleaning")

    df = df.join(play_cols, on="playId", how="left").with_columns(
        pl.when(pl.col("event") == "None").then(None).otherwise(pl.col("event")).alias("event"),
        pl.col("time").str.to_datetime(time_unit="ms", time_zone="UTC", strict=False).alias("time"),
    )
    log.check("tracking.unparsed_time", df["time"].is_null().sum(), detail="timestamp not parseable",
              total=df.height)
    is_ball = (pl.col("team") == "football").fill_null(False)
    df = df.with_columns(
        pl.when(is_ball).then(pl.lit("ball"))
        .when(pl.col("team") == pl.col("possessionTeam")).then(pl.lit("offense"))
        .when(pl.col("team") == pl.col("defensiveTeam")).then(pl.lit("defense"))
        .otherwise(pl.lit("unknown")).alias("side"))

    # --- Field direction: standardize so the offense always moves toward increasing x. ---
    flip = pl.col("playDirection") == "left"
    valid_dir = pl.col("playDirection").is_in(["left", "right"])
    los_raw = pl.col("absoluteYardlineNumber").cast(pl.Float64)  # same frame as raw x (verified)
    ang = lambda c: pl.when(flip).then((pl.col(c) + 180.0) % 360.0).otherwise(pl.col(c))  # noqa: E731
    df = df.with_columns(
        pl.when(valid_dir).then(pl.when(flip).then(FIELD_LENGTH - pl.col("x")).otherwise(pl.col("x"))).alias("x_std"),
        pl.when(valid_dir).then(pl.when(flip).then(FIELD_WIDTH - pl.col("y")).otherwise(pl.col("y"))).alias("y_std"),
        pl.when(valid_dir).then(ang("o")).alias("o_std"),
        pl.when(valid_dir).then(ang("dir")).alias("dir_std"),
        pl.when(valid_dir).then(pl.when(flip).then(FIELD_LENGTH - los_raw).otherwise(los_raw)).alias("_los_std"),
    ).with_columns(
        (pl.col("x_std") - pl.col("_los_std")).alias("x_rel_los"),
        # dir: 0 deg = +y, 90 deg = +x (clockwise); velocity from speed and dir.
        (pl.col("s") * pl.col("dir_std").radians().sin()).alias("vx_std"),
        (pl.col("s") * pl.col("dir_std").radians().cos()).alias("vy_std"),
    ).drop("_los_std")

    # --- Snap / pass events (frame numbers) ---
    snap = _first_frame(df, SNAP_EVENTS, "snap_frame")
    throw = _first_frame(df, PASS_FORWARD_EVENTS, "pass_forward_frame")
    n_snap = (df.filter(pl.col("event") == "ball_snap").group_by("playId")
              .agg(pl.col("frameId").n_unique().alias("n_ball_snap_frames")))
    df = df.join(snap.select("playId", "snap_frame"), on="playId", how="left").with_columns(
        (pl.col("frameId") - pl.col("snap_frame")).cast(pl.Int32).alias("frames_since_snap")
    ).drop("snap_frame")

    # --- Distances to ball and QB (same play/frame; no all-to-all join) ---
    ball = (df.filter(pl.col("side") == "ball").unique(subset=["playId", "frameId"], keep="first")
            .select("playId", "frameId", pl.col("x").alias("_bx"), pl.col("y").alias("_by")))
    qb_map = (pff.filter(pl.col("pff_role") == "Pass").select("playId", pl.col("nflId").alias("_qb"))
              .unique(subset="playId", keep="first"))
    df = df.join(qb_map, on="playId", how="left")
    qb_pos = (df.filter(pl.col("nflId") == pl.col("_qb"))
              .select("playId", "frameId", pl.col("x").alias("_qx"), pl.col("y").alias("_qy")))
    hyp = lambda x, y, x0, y0: ((pl.col(x) - pl.col(x0)) ** 2 + (pl.col(y) - pl.col(y0)) ** 2).sqrt()  # noqa: E731
    df = (df.join(ball, on=["playId", "frameId"], how="left")
          .join(qb_pos, on=["playId", "frameId"], how="left")
          .with_columns(
              pl.when(pl.col("side") != "ball").then(hyp("x", "y", "_bx", "_by")).alias("dist_to_ball"),
              pl.when(pl.col("nflId").is_null() | (pl.col("nflId") != pl.col("_qb")))
              .then(hyp("x", "y", "_qx", "_qy")).alias("dist_to_qb"))
          .drop("_bx", "_by", "_qx", "_qy"))
    df = df.join(_proximity(df), on=["playId", "frameId", "nflId"], how="left")

    # --- Validation flags (rows kept) ---
    lim_p, lim_b = LIMITS["player"], LIMITS["ball"]
    lim = lambda k: pl.when(pl.col("side") == "ball").then(lim_b[k]).otherwise(lim_p[k])  # noqa: E731
    flags = (
        pl.when(~pl.col("x").is_between(*X_RANGE) | ~pl.col("y").is_between(*Y_RANGE)).then(FLAG_POSITION).otherwise(0)
        + pl.when(pl.col("s") > lim("s")).then(FLAG_SPEED).otherwise(0)
        + pl.when(pl.col("a").abs() > lim("a")).then(FLAG_ACCEL).otherwise(0)
        + pl.when(pl.col("dis") > lim("dis")).then(FLAG_DIS).otherwise(0)
        + pl.when(pl.any_horizontal([pl.col(c).is_null() for c in ("x", "y", "s", "a", "dis")]))
        .then(FLAG_MISSING_CORE).otherwise(0)
        + pl.when(pl.col("side") == "unknown").then(FLAG_UNKNOWN_SIDE).otherwise(0)
        + pl.when(~valid_dir).then(FLAG_BAD_DIRECTION).otherwise(0)
    )
    df = df.with_columns(flags.cast(pl.UInt8).alias("qc_flags"))
    for bit, name in FLAG_NAMES.items():
        n = df.filter((pl.col("qc_flags") & bit) > 0).height
        log.check(f"tracking.flag.{name}", n, detail="rows flagged, kept in output", total=df.height)

    # --- Play-level metadata and consistency checks ---
    frame_stats = df.group_by("playId", "frameId").agg(
        pl.len().alias("n_ent"),
        (pl.col("side") == "ball").sum().alias("n_ball"),
        pl.col("side").is_in(["offense", "defense"]).sum().alias("n_players"))
    per_play_frames = frame_stats.group_by("playId").agg(
        pl.len().alias("n_frames"), pl.col("frameId").min().alias("min_frame"),
        pl.col("frameId").max().alias("max_frame"),
        (pl.col("n_ent") != ENTITIES_PER_FRAME).sum().alias("frames_bad_entity_count"),
        (pl.col("n_ball") != 1).sum().alias("frames_bad_ball_count"),
        (pl.col("n_players") != PLAYERS_PER_FRAME).sum().alias("frames_players_not_22"))
    per_play_frames = per_play_frames.with_columns(
        (pl.col("max_frame") - pl.col("min_frame") + 1 - pl.col("n_frames")).alias("frame_gaps"))
    per_play_rows = df.group_by("playId").agg(
        pl.col("playDirection").n_unique().alias("n_directions"),
        pl.col("playDirection").first().alias("playDirection"),
        pl.col("nflId").drop_nulls().n_unique().alias("n_tracked_players"),
        ((pl.col("qc_flags") > 0) & (pl.col("side") != "ball")).sum().alias("n_flagged_rows"),
        ((pl.col("qc_flags") > 0) & (pl.col("side") == "ball")).sum().alias("n_ball_flagged_rows"))
    snap_ball = (df.filter(pl.col("side") == "ball").join(snap.select("playId", "snap_frame"), on="playId")
                 .filter(pl.col("frameId") == pl.col("snap_frame"))
                 .group_by("playId").agg(pl.col("x").first().alias("ball_x_at_snap_raw")))

    ids = df.filter(pl.col("nflId").is_not_null()).select("playId", "nflId").unique()
    pff_pairs = pff.select("playId", "nflId").unique()
    cnt = lambda d, n: d.group_by("playId").agg(pl.len().alias(n))  # noqa: E731
    meta = (per_play_frames.join(per_play_rows, on="playId")
            .join(snap, on="playId", how="left").join(throw, on="playId", how="left")
            .join(n_snap, on="playId", how="left").join(snap_ball, on="playId", how="left")
            .join(play_cols.select("playId", pl.col("absoluteYardlineNumber").alias("los_x_raw")),
                  on="playId", how="left")
            .join(qb_map.rename({"_qb": "qb_nflId"}), on="playId", how="left")
            .join(cnt(ids.join(pff_pairs, on=["playId", "nflId"], how="anti"), "n_tracked_not_in_pff"),
                  on="playId", how="left")
            .join(cnt(pff_pairs.join(ids, on=["playId", "nflId"], how="anti"), "n_pff_not_in_tracking"),
                  on="playId", how="left")
            .join(cnt(ids.filter(~pl.col("nflId").is_in(list(player_ids))), "n_tracked_not_in_players_csv"),
                  on="playId", how="left"))
    qb_tracked = df.filter(pl.col("nflId") == pl.col("_qb")).select("playId").unique().with_columns(
        pl.lit(True).alias("qb_in_tracking"))
    meta = meta.join(qb_tracked, on="playId", how="left").with_columns(
        pl.col("qb_in_tracking").fill_null(False),
        pl.col("n_ball_snap_frames").fill_null(0),
        pl.col("n_tracked_not_in_pff", "n_pff_not_in_tracking", "n_tracked_not_in_players_csv").fill_null(0),
        (pl.col("ball_x_at_snap_raw") - pl.col("los_x_raw")).abs().alias("los_diff"),
        ((pl.col("pass_forward_frame") - pl.col("snap_frame")) / 10.0).alias("time_to_throw_s"),
    ).with_columns((pl.col("los_diff") <= LOS_TOLERANCE_YDS).alias("los_consistent"))
    meta = meta.with_columns(
        ((pl.col("frame_gaps") == 0) & (pl.col("min_frame") == 1) & (pl.col("frames_bad_entity_count") == 0)
         & (pl.col("frames_bad_ball_count") == 0) & (pl.col("n_directions") == 1)
         & pl.col("snap_frame").is_not_null() & pl.col("qb_in_tracking")
         & (pl.col("n_flagged_rows") == 0)).alias("qc_pass"))

    n = meta.height
    for name, cond in {
        "play.frame_gaps": pl.col("frame_gaps") > 0,
        "play.first_frame_not_1": pl.col("min_frame") != 1,
        "play.frames_with_wrong_entity_count": pl.col("frames_bad_entity_count") > 0,
        "play.frames_without_single_ball": pl.col("frames_bad_ball_count") > 0,
        "play.frames_players_not_22": pl.col("frames_players_not_22") > 0,
        "play.multiple_directions": pl.col("n_directions") != 1,
        "play.no_snap_event": pl.col("snap_frame").is_null(),
        "play.multiple_ball_snap_frames": pl.col("n_ball_snap_frames") > 1,
        "play.no_pass_forward_event": pl.col("pass_forward_frame").is_null(),
        "play.qb_not_in_tracking": ~pl.col("qb_in_tracking"),
        "play.los_inconsistent": pl.col("los_consistent") == False,  # noqa: E712
        "play.los_unverifiable": pl.col("los_consistent").is_null(),
        "play.tracked_not_in_pff": pl.col("n_tracked_not_in_pff") > 0,
        "play.pff_not_in_tracking": pl.col("n_pff_not_in_tracking") > 0,
        "play.tracked_not_in_players_csv": pl.col("n_tracked_not_in_players_csv") > 0,
    }.items():
        sev = "info" if name in ("play.no_pass_forward_event", "play.frames_players_not_22") else "warn"
        log.check(name, meta.filter(cond).height, severity=sev, total=n)
    log.check("play.ball_has_flagged_rows", meta.filter(pl.col("n_ball_flagged_rows") > 0).height,
              severity="info", total=n, detail="ball dis/speed jumps; does not affect qc_pass")
    log.check("play.qc_pass", meta.filter(~pl.col("qc_pass")).height, severity="info", total=n,
              detail="plays failing a structural check or with flagged player rows (not removed)")
    meta = meta.with_columns(pl.lit(game_id).alias("gameId"))

    out = (df.select(OUT_COLS).sort("playId", "frameId", "nflId", nulls_last=True)
           .with_columns([pl.col(c).cast(pl.Float32) for c in
                          ("vx_std", "vy_std", "dist_to_ball", "dist_to_qb", "nearest_opp_dist")]))
    return out, meta.sort("playId")
