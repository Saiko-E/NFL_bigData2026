"""Independent validation of processed outputs (re-derived from the Parquet files, not from ETL logs)."""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import connect
from .config import FIELD_LENGTH, Paths
from .io import write_json_atomic


@dataclass
class Result:
    name: str
    passed: bool
    detail: str
    critical: bool = True


def validate(paths: Paths | None = None, write_report: bool = True) -> list[Result]:
    paths = paths or Paths.default()
    con = connect(paths)
    q = lambda s: con.execute(s).fetchall()  # noqa: E731
    one = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    res: list[Result] = []

    def add(name: str, passed: bool, detail: str, critical: bool = True) -> None:
        res.append(Result(name, bool(passed), detail, critical))

    existing = {r[0] for r in q("SELECT view_name FROM duckdb_views() WHERE NOT internal")}
    need = ["games", "plays", "players", "pff", "tracking", "play_meta", "events", "play_summary",
            "player_play", "player_summary", "team_summary", "game_summary"]
    missing = [n for n in need if n not in existing]
    add("outputs_exist", not missing, f"missing: {missing}" if missing else f"{len(need)} datasets present")
    if missing:
        return _finish(paths, res, write_report)

    n_games = one("SELECT count(DISTINCT gameId) FROM tracking")
    n_rows = one("SELECT count(*) FROM tracking")
    add("tracking_non_empty", n_rows > 0, f"{n_rows:,} rows, {n_games} games")

    dup = one("""SELECT count(*) FROM (SELECT gameId, playId, frameId, coalesce(nflId, -1) k FROM tracking
                 GROUP BY ALL HAVING count(*) > 1)""")
    add("tracking_unique_key", dup == 0, f"{dup} duplicate (game, play, frame, entity) keys")

    add("fk_tracking_play_in_plays", one("""SELECT count(*) FROM (SELECT DISTINCT gameId, playId FROM tracking) t
        ANTI JOIN plays p USING (gameId, playId)""") == 0, "every tracked play exists in plays")
    add("fk_tracking_player_in_players", one("""SELECT count(*) FROM (SELECT DISTINCT nflId FROM tracking
        WHERE nflId IS NOT NULL) t ANTI JOIN players p USING (nflId)""") == 0,
        "every tracked nflId exists in players")
    add("fk_plays_game_in_games", one("SELECT count(*) FROM plays ANTI JOIN games USING (gameId)") == 0,
        "every play's game exists")
    add("fk_pff_play_and_player", one("""SELECT count(*) FROM pff f ANTI JOIN plays p USING (gameId, playId)""")
        + one("SELECT count(*) FROM pff f ANTI JOIN players p USING (nflId)") == 0,
        "every PFF row maps to a play and a player")

    nf = one("SELECT count(*) FROM tracking WHERE nflId IS NULL AND side <> 'ball'")
    nb = one("SELECT count(*) FROM tracking WHERE nflId IS NOT NULL AND side = 'ball'")
    add("ball_rows_have_null_nflId", nf == 0 and nb == 0,
        f"{nf} non-ball rows without nflId, {nb} ball rows with nflId")

    gaps = one("""SELECT count(*) FROM (SELECT gameId, playId FROM tracking GROUP BY ALL
        HAVING max(frameId) - min(frameId) + 1 <> count(DISTINCT frameId) OR min(frameId) <> 1)""")
    add("frames_contiguous_from_1", gaps == 0, f"{gaps} plays with gaps or first frame != 1", critical=False)

    unsorted = one("""SELECT count(*) FROM (SELECT filename, file_row_number, playId, frameId,
        lag(playId) OVER w AS pp, lag(frameId) OVER w AS pf
        FROM read_parquet('{g}', filename=true, file_row_number=true, hive_partitioning=false)
        WINDOW w AS (PARTITION BY filename ORDER BY file_row_number))
        WHERE pp IS NOT NULL AND (playId < pp OR (playId = pp AND frameId < pf))""".format(
        g=(paths.tracking / "*" / "*.parquet").as_posix()))
    add("tracking_sorted_by_play_frame", unsorted == 0, f"{unsorted} out-of-order rows")

    # Standardization: raw coordinates preserved and standardized x consistent with direction.
    bad_x = one(f"""SELECT count(*) FROM tracking WHERE playDirection IN ('left','right') AND
        abs(x_std - CASE WHEN playDirection = 'left' THEN {FIELD_LENGTH} - x ELSE x END) > 1e-6""")
    add("x_std_matches_direction", bad_x == 0, f"{bad_x} rows where x_std != normalized raw x")
    # Orientation sanity: at the snap the QB is behind the line of scrimmage in the standardized frame.
    row = q("""SELECT count(*) FILTER (x_rel_los < 0), count(*) FROM tracking t JOIN play_meta m USING (gameId, playId)
        WHERE t.nflId = m.qb_nflId AND t.frameId = m.snap_frame""")[0]
    frac = row[0] / row[1] if row[1] else 0.0
    add("qb_behind_los_at_snap_after_normalization", frac >= 0.95,
        f"{row[0]:,}/{row[1]:,} plays ({frac:.1%}) have QB at x_rel_los < 0 (expect >= 95%)")
    both = q("""SELECT avg(CASE WHEN off.m < def.m THEN 1.0 ELSE 0.0 END), count(*) FROM
        (SELECT gameId, playId, avg(x_std) m FROM tracking t JOIN play_meta USING (gameId, playId)
         WHERE side = 'offense' AND frameId = snap_frame GROUP BY ALL) off JOIN
        (SELECT gameId, playId, avg(x_std) m FROM tracking t JOIN play_meta USING (gameId, playId)
         WHERE side = 'defense' AND frameId = snap_frame GROUP BY ALL) def USING (gameId, playId)""")[0]
    add("offense_left_of_defense_at_snap", (both[0] or 0) >= 0.95,
        f"offense mean x_std < defense mean x_std in {(both[0] or 0):.1%} of {both[1]:,} plays")

    ranges = q("""SELECT min(x), max(x), min(y), max(y), max(s) FILTER (side <> 'ball'),
                  max(abs(a)) FILTER (side <> 'ball') FROM tracking""")[0]
    add("value_ranges_plausible", -10 <= ranges[0] and ranges[1] <= 130 and -10 <= ranges[2]
        and ranges[3] <= 63 and ranges[4] <= 20, "x[{:.1f},{:.1f}] y[{:.1f},{:.1f}] max player s={:.1f} |a|={:.1f}"
        .format(*ranges))
    flagged = one("SELECT count(*) FROM tracking WHERE qc_flags > 0")
    add("flagged_rows_reported", True, f"{flagged:,} rows ({flagged / n_rows:.3%}) have qc_flags > 0; kept in output",
        critical=False)

    dist = q("""SELECT median(abs(dis - sqrt(power(x - px, 2) + power(y - py, 2)))) FROM
        (SELECT dis, x, y, lag(x) OVER w px, lag(y) OVER w py FROM tracking WHERE side <> 'ball'
         WINDOW w AS (PARTITION BY gameId, playId, nflId ORDER BY frameId)) WHERE px IS NOT NULL""")[0][0]
    add("dis_matches_position_change", dist is not None and dist < 0.02,
        f"median |dis - displacement| = {dist:.4f} yd (expect < 0.02)")

    pm_plays = one("SELECT count(*) FROM play_meta")
    tr_plays = one("SELECT count(*) FROM (SELECT DISTINCT gameId, playId FROM tracking)")
    add("play_meta_matches_tracking", pm_plays == tr_plays, f"play_meta={pm_plays}, tracking plays={tr_plays}")
    ps = one("SELECT count(*) FROM play_summary")
    pl_ = one("SELECT count(*) FROM plays")
    add("play_summary_covers_plays", ps == pl_, f"play_summary={ps}, plays={pl_}")
    comp = q("""SELECT compression FROM parquet_metadata('{g}') GROUP BY ALL""".format(
        g=(paths.tracking / "*" / "*.parquet").as_posix()))
    add("tracking_parquet_zstd", {c[0] for c in comp} == {"ZSTD"}, f"compression: {[c[0] for c in comp]}")

    manif_ok = one("SELECT count(DISTINCT gameId) FROM play_meta")
    add("games_processed", manif_ok == n_games, f"{manif_ok} games in play_meta vs {n_games} in tracking")
    return _finish(paths, res, write_report)


def _finish(paths: Paths, res: list[Result], write_report: bool) -> list[Result]:
    if write_report:
        write_json_atomic([r.__dict__ for r in res], paths.reports / "validation.json")
    return res
