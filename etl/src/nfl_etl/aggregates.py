"""Basic aggregates built with DuckDB from the processed Parquet files.

Definitions (also in docs/DATA_DICTIONARY.md):
- window: frames from the snap (frames_since_snap = 0) to the pass-forward frame (inclusive);
  if the play has no pass-forward event (e.g. some sacks), the window ends at the last frame.
- Kinematic metrics only use rows where qc_flags has none of speed/accel/dis/missing bits (30).
- Pressure (PFF): a pass rusher with pff_hit, pff_hurry or pff_sack = 1 in that play.
"""
from __future__ import annotations

import os
from pathlib import Path

from .catalog import connect
from .config import Paths

KIN_OK = "(t.qc_flags & 30) = 0"


def _copy(con, query: str, out: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    con.execute(f"COPY ({query}) TO '{tmp.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, out)
    return con.execute(f"SELECT count(*) FROM read_parquet('{out.as_posix()}')").fetchone()[0]


def build_events(paths: Paths) -> int:
    con = connect(paths, only=["tracking"])
    q = """SELECT DISTINCT gameId, playId, frameId, event FROM tracking
           WHERE event IS NOT NULL ORDER BY gameId, playId, frameId, event"""
    return _copy(con, q, paths.processed / "events" / "events.parquet")


def build_aggregates(paths: Paths) -> dict[str, int]:
    """(Re)build all aggregate tables. Safe to run repeatedly; output is fully overwritten."""
    con = connect(paths, only=["games", "plays", "players", "pff", "tracking", "play_meta"])
    counts: dict[str, int] = {}
    counts["events"] = build_events(paths)

    # Play-level: plays + tracking meta + PFF counts. Only plays present in tracking get meta columns.
    con.execute("""
    CREATE TEMP TABLE pff_play AS
    SELECT gameId, playId,
      count(*) FILTER (pff_role = 'Pass Rush') AS n_pass_rushers,
      count(*) FILTER (pff_role = 'Pass Block') AS n_pass_blockers,
      count(*) FILTER (pff_role = 'Coverage') AS n_coverage,
      count(*) FILTER (pff_role = 'Pass Route') AS n_routes,
      count(*) FILTER (pff_hit) AS n_hits,
      count(*) FILTER (pff_hurry) AS n_hurries,
      count(*) FILTER (pff_sack) AS n_sacks_pff,
      count(*) FILTER (pff_hit OR pff_hurry OR pff_sack) AS n_pressure_rushers,
      count(*) FILTER (pff_beatenByDefender) AS n_blockers_beaten
    FROM pff GROUP BY ALL""")
    q = """
    SELECT p.*, m.n_frames, m.snap_frame, m.snap_frame_event, m.pass_forward_frame, m.pass_forward_frame_event,
           coalesce(m.pass_forward_frame, m.max_frame) AS window_end_frame,
           m.time_to_throw_s, m.qb_nflId, m.los_consistent, m.qc_pass, m.n_flagged_rows,
           f.n_pass_rushers, f.n_pass_blockers, f.n_coverage, f.n_routes, f.n_hits, f.n_hurries,
           f.n_sacks_pff, f.n_pressure_rushers, f.n_blockers_beaten,
           coalesce(f.n_pressure_rushers, 0) > 0 AS has_pressure,
           m.gameId IS NOT NULL AS has_tracking
    FROM plays p
    LEFT JOIN play_meta m USING (gameId, playId)
    LEFT JOIN pff_play f USING (gameId, playId)
    ORDER BY p.gameId, p.playId"""
    counts["play_summary"] = _copy(con, q, paths.agg / "play_summary.parquet")

    # Player-play level (tracking window metrics + PFF assignment/outcome).
    con.execute(f"""
    CREATE TEMP TABLE pp AS
    SELECT t.gameId, t.playId, t.nflId, any_value(t.team) AS team, any_value(t.side) AS side,
      count(*) AS n_frames,
      sum(t.dis) FILTER ({KIN_OK}) AS dist_total_yds,
      sum(t.dis) FILTER ({KIN_OK} AND t.frames_since_snap BETWEEN 1 AND s.window_end_frame - s.snap_frame)
        AS dist_window_yds,
      max(t.s) FILTER ({KIN_OK} AND t.frames_since_snap >= 0) AS max_speed_yps,
      avg(t.s) FILTER ({KIN_OK} AND t.frames_since_snap BETWEEN 0 AND s.window_end_frame - s.snap_frame)
        AS avg_speed_window_yps,
      max(abs(t.a)) FILTER ({KIN_OK} AND t.frames_since_snap >= 0) AS max_abs_accel_ypss,
      min(t.dist_to_qb) FILTER (t.frames_since_snap BETWEEN 0 AND s.window_end_frame - s.snap_frame)
        AS min_dist_to_qb_window,
      avg(t.dist_to_qb) FILTER (t.frames_since_snap BETWEEN 0 AND s.window_end_frame - s.snap_frame)
        AS avg_dist_to_qb_window,
      min(t.nearest_opp_dist) FILTER (t.frames_since_snap BETWEEN 0 AND s.window_end_frame - s.snap_frame)
        AS min_dist_to_opp_window,
      any_value(t.x_rel_los) FILTER (t.frames_since_snap = 0) AS x_rel_los_at_snap,
      any_value(t.y_std) FILTER (t.frames_since_snap = 0) AS y_std_at_snap
    FROM tracking t
    JOIN (SELECT gameId, playId, snap_frame, coalesce(pass_forward_frame, max_frame) AS window_end_frame
          FROM play_meta) s USING (gameId, playId)
    WHERE t.side IN ('offense', 'defense') AND s.snap_frame IS NOT NULL
    GROUP BY t.gameId, t.playId, t.nflId""")
    q = """
    SELECT pp.*, pl.officialPosition, pl.positionGroup,
      f.pff_role, f.pff_positionLinedUp, f.pff_hit, f.pff_hurry, f.pff_sack, f.pff_beatenByDefender,
      f.pff_hitAllowed, f.pff_hurryAllowed, f.pff_sackAllowed, f.pff_nflIdBlockedPlayer,
      f.pff_blockType, f.pff_backFieldBlock
    FROM pp
    LEFT JOIN players pl USING (nflId)
    LEFT JOIN pff f USING (gameId, playId, nflId)
    ORDER BY gameId, playId, nflId"""
    counts["player_play"] = _copy(con, q, paths.agg / "player_play.parquet")
    con.execute(f"CREATE OR REPLACE VIEW player_play AS SELECT * FROM read_parquet('{(paths.agg / 'player_play.parquet').as_posix()}')")

    q = """
    SELECT pl.nflId, pl.displayName, pl.officialPosition, pl.positionGroup,
      count(*) AS n_plays, count(DISTINCT pp.gameId) AS n_games,
      string_agg(DISTINCT pp.team, ',' ORDER BY pp.team) AS teams,
      count(*) FILTER (pp.side = 'offense') AS n_plays_offense,
      count(*) FILTER (pp.side = 'defense') AS n_plays_defense,
      avg(pp.dist_window_yds) AS avg_dist_window_yds,
      avg(pp.avg_speed_window_yps) AS avg_speed_window_yps,
      max(pp.max_speed_yps) AS top_speed_yps,
      avg(pp.max_abs_accel_ypss) AS avg_max_abs_accel_ypss,
      count(*) FILTER (pp.pff_role = 'Pass Rush') AS n_pass_rush,
      count(*) FILTER (pp.pff_hit) AS hits,
      count(*) FILTER (pp.pff_hurry) AS hurries,
      count(*) FILTER (pp.pff_sack) AS sacks,
      count(*) FILTER (pp.pff_role = 'Pass Block') AS n_pass_block,
      count(*) FILTER (pp.pff_hitAllowed) AS hits_allowed,
      count(*) FILTER (pp.pff_hurryAllowed) AS hurries_allowed,
      count(*) FILTER (pp.pff_sackAllowed) AS sacks_allowed,
      count(*) FILTER (pp.pff_beatenByDefender) AS beaten_by_defender,
      count(*) FILTER (pp.pff_role = 'Coverage') AS n_coverage,
      count(*) FILTER (pp.pff_role = 'Pass Route') AS n_routes
    FROM player_play pp JOIN players pl USING (nflId)
    GROUP BY ALL ORDER BY pl.nflId"""
    counts["player_summary"] = _copy(con, q, paths.agg / "player_summary.parquet")

    con.execute(f"CREATE OR REPLACE VIEW play_summary AS SELECT * FROM read_parquet('{(paths.agg / 'play_summary.parquet').as_posix()}')")
    team_q = lambda side, col: f"""
    SELECT {col} AS team, '{side}' AS side, count(*) AS n_plays, count(DISTINCT gameId) AS n_games,
      count(*) FILTER (passResult = 'C') AS n_complete, count(*) FILTER (passResult = 'I') AS n_incomplete,
      count(*) FILTER (passResult = 'S') AS n_sack, count(*) FILTER (passResult = 'R') AS n_scramble,
      count(*) FILTER (passResult = 'IN') AS n_interception,
      count(*) FILTER (has_pressure) AS n_pressure_plays,
      count(*) FILTER (has_tracking) AS n_tracked_plays,
      avg(time_to_throw_s) AS avg_time_to_throw_s, avg(playResult) AS avg_play_result,
      avg(yardsToGo) AS avg_yards_to_go
    FROM play_summary GROUP BY {col}"""
    q = f"{team_q('offense', 'possessionTeam')} UNION ALL {team_q('defense', 'defensiveTeam')} ORDER BY team, side"
    counts["team_summary"] = _copy(con, q, paths.agg / "team_summary.parquet")

    q = """
    SELECT g.gameId, g.season, g.week, g.gameDate, g.homeTeamAbbr, g.visitorTeamAbbr,
      count(p.playId) AS n_plays, count(*) FILTER (p.has_tracking) AS n_tracked_plays,
      count(*) FILTER (p.qc_pass) AS n_qc_pass_plays,
      count(*) FILTER (p.passResult = 'S') AS n_sack, count(*) FILTER (p.has_pressure) AS n_pressure_plays,
      avg(p.time_to_throw_s) AS avg_time_to_throw_s
    FROM games g LEFT JOIN play_summary p USING (gameId) GROUP BY ALL ORDER BY g.gameId"""
    counts["game_summary"] = _copy(con, q, paths.agg / "game_summary.parquet")
    return counts
