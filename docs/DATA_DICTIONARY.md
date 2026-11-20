# Data dictionary

All facts below were verified on the real files (Phase 1) unless marked "assumption". Original column meanings: `docs/BDB_SOURCE_README.md`.

## Source files (`data/raw/`)
| File | Rows | Key | Notes |
|---|---:|---|---|
| `games.csv` | 122 | `gameId` | season 2021, weeks 1-8 |
| `plays.csv` | 8,557 | `gameId, playId` | pass plays only; `playId` is not unique across games |
| `players.csv` | 1,679 | `nflId` | |
| `pffScoutingData.csv` | 188,254 | `gameId, playId, nflId` | exactly 22 rows per play (8,557 x 22) |
| `tracking/tracking_<gameId>.csv` | 8,314,178 (122 files) | `gameId, playId, frameId, nflId` | 23 entities per frame: 22 players + ball |

Null convention: every source file writes missing values as the literal `NA`. Tracking `event` uses the literal `None` for "no event". The ETL converts both to real nulls.

## Relationships
`games 1-n plays` (gameId) · `plays 1-n pff` (gameId, playId) · `players 1-n pff` (nflId) · `plays 1-n tracking` (gameId, playId) · `players 1-n tracking` (nflId; null for the ball). Verified: no orphan keys in any direction; every tracked player appears in the same play's PFF rows and the reverse.
`pff_nflIdBlockedPlayer` points to another PFF row in the same play, except 2 rows where it does not (logged as a warning).

## Tracking facts
- Field frame: `x` 0-120 yd along the length (end zones included), `y` 0-53.3 yd across. `s` yd/s, `a` yd/s², `dis` yd since the previous frame, `o` and `dir` degrees (0 = +y, 90 = +x).
- `frameId` starts at 1 in every play and has no gaps. 10 Hz. `time` has 1 s resolution (about 10 consecutive frames share a timestamp): use `frameId`, not `time`, for animation.
- Football rows: `team='football'`, `nflId`, `jerseyNumber`, `o`, `dir` are null.
- `playDirection` is the direction the offense moves (`left`/`right`). `absoluteYardlineNumber` is in the same raw `x` frame as the tracking (verified: ball x at snap is within 3 yd of it in 8,473 of 8,532 checked plays; the others are 3-8 yd off and logged as `play.los_inconsistent`).
- `dis` equals the position change between frames (median error 0.003 yd), so summing `dis` gives distance traveled.
- Players and the ball can be up to about 4 yd outside the field lines (x from -3.55 to 121.15, y from -4.53 to 57.72).
- Observed player maxima: speed 11.2 yd/s, |acceleration| 21.9 yd/s². The ball reaches s 29.3 yd/s and |a| 50.7 yd/s². Its `dis` goes above 3.5 yd/frame in 4,194 rows (maximum 10.45), which matches its position changes but is far above any real ball speed, so it looks like tracking noise.
- Events (play-frame counts over all 122 games): `ball_snap` 8,532, `pass_forward` 7,548, `autoevent_ballsnap` 3,767, `autoevent_passforward` 3,734, `play_action` 1,977, `run` 474, `qb_sack` 451, `pass_arrived` 367, `autoevent_passinterrupted` 201, `man_in_motion` 177, `line_set` 140, `shift` 133, `pass_tipped` 111, `first_contact` 80, `qb_strip_sack` 58, `pass_outcome_incomplete` 40, `pass_outcome_caught` 23, `fumble` 17, `fumble_offense_recovered` 11, `handoff` 10, and a few others (`huddle_break_offense`, `tackle`, `penalty_flag`, `dropped_pass`, `lateral`, `out_of_bounds`). Each event is repeated on all 23 rows of its frame (verified).
- 24 plays have no snap event; 953 plays have no pass-forward event (513 sacks, 437 scrambles, 3 others).

## Processed outputs (`data/processed/`)
Parquet, zstd compressed. View names are those of `nfl_etl.catalog.connect()`.

| View | Path | Rows | Grain |
|---|---|---:|---|
| `games`, `plays`, `players`, `pff` | `dim/*.parquet` | 122 / 8,557 / 1,679 / 188,254 | cleaned sources |
| `tracking` | `tracking/week=W/part-<gameId>.parquet` | 8,314,178 | game, play, frame, entity |
| `play_meta` | `play_meta/<gameId>.parquet` | 8,557 | play (tracking QC and event frames) |
| `events` | `events/events.parquet` | 27,862 | play, frame, event |
| `play_summary` | `agg/play_summary.parquet` | 8,557 | play (plays + play_meta + PFF counts) |
| `player_play` | `agg/player_play.parquet` | 187,726 | player in play (8,533 plays with a snap x 22) |
| `player_summary` | `agg/player_summary.parquet` | 1,679 | player |
| `team_summary` | `agg/team_summary.parquet` | 64 | team x side (offense/defense) |
| `game_summary` | `agg/game_summary.parquet` | 122 | game |

### Cleaning applied to dimensions
- `games.gameDate` -> date; `gameTimeEastern` -> time.
- `players.height` "6-4" -> `heightInches` (76). `birthDate` accepts `YYYY-MM-DD` and `MM/DD/YYYY` (both occur; 232 are null). `positionGroup` maps `officialPosition`: QB; RB (RB, FB); WR; TE; OL (T, G, C); DL (DE, DT, NT); LB (OLB, ILB, MLB, LB); DB (CB, FS, SS, DB).
- `plays`: adds `gameClockSeconds`, `isSack` (passResult = S), `formationMissing`, `scoreDiffOffense` (offense minus defense score before the snap), `week`.
- `pff`: the eight 0/1 flags become booleans. Null means the flag does not apply to that role (for example hit/hurry/sack exist only for pass rushers).
- `passResult`: C complete, I incomplete, S sack, R scramble, IN interception.

### `tracking` derived columns
| Column | Definition |
|---|---|
| `side` | `ball`, `offense` (team = possessionTeam), `defense` (team = defensiveTeam), or `unknown` (flagged) |
| `x_std`, `y_std` | `x`, `y` for `right` plays; `120 - x`, `53.3 - y` for `left` plays. Offense always moves toward +x |
| `o_std`, `dir_std` | `o`, `dir` for `right`; `(angle + 180) mod 360` for `left` |
| `vx_std`, `vy_std` | `s * sin(dir_std)`, `s * cos(dir_std)`: velocity components in yd/s. No acceleration vector (the data gives only its magnitude) |
| `x_rel_los` | `x_std` minus the line of scrimmage in the standardized frame. Negative = behind the line (offense side) |
| `frames_since_snap` | `frameId - snap_frame` (negative before the snap; null if the play has no snap event). Divide by 10 for seconds |
| `dist_to_ball` | distance to the football in the same frame (null for the ball) |
| `dist_to_qb` | distance to the QB in the same frame. QB = the PFF row with role `Pass`. Null for the QB itself and where the QB is not tracked |
| `nearest_opp_dist`, `nearest_opp_id` | nearest opposing player (offense vs defense only) in the same frame. Null for the ball |
| `qc_flags` | bit mask, rows are kept: 1 position outside x[-5,125] or y[-5,58.3]; 2 speed above limit; 4 \|a\| above limit; 8 `dis` above limit; 16 null x/y/s/a/dis; 32 unknown side; 64 bad `playDirection` |
| `week` | hive partition column from the directory name |

Limits: players s 15, \|a\| 25, dis 2.5; ball s 45, \|a\| 80, dis 3.5. They sit above the maxima observed in the data, so flags mark outliers, not normal play.

### `play_meta`
`snap_frame` (first `ball_snap`, else first `autoevent_ballsnap`), `snap_frame_event`, `pass_forward_frame` (first `pass_forward`, else `autoevent_passforward`), `time_to_throw_s = (pass_forward_frame - snap_frame) / 10`, `n_frames`, `qb_nflId`, `qb_in_tracking`, `ball_x_at_snap_raw`, `los_x_raw`, `los_diff`, `los_consistent` (diff <= 3 yd), frame and entity consistency counts, `n_flagged_rows` (player rows with `qc_flags > 0`), `n_ball_flagged_rows`, and `qc_pass`.
`qc_pass` is true when: no frame gaps, first frame is 1, 23 entities and one ball in every frame, one play direction, a snap event, QB tracked, and no flagged player rows. 8,528 of 8,557 plays pass; the failures are the 24 plays without a snap and 5 with flagged player rows. Plays that fail are kept.

### Aggregate metric definitions
- Window: frames from the snap to the pass-forward frame inclusive; if there is no pass-forward event, to the last frame. Stored per play as `window_end_frame` in `play_summary`.
- Kinematic metrics (`dist_*`, speeds, accelerations) skip rows whose `qc_flags` has the speed, accel, dis or missing bits.
- `player_play`: `dist_total_yds` (sum of `dis`), `dist_window_yds` (after the snap, inside the window), `max_speed_yps`, `avg_speed_window_yps`, `max_abs_accel_ypss`, `min_dist_to_qb_window`, `avg_dist_to_qb_window`, `min_dist_to_opp_window`, `x_rel_los_at_snap`, `y_std_at_snap`, plus position, PFF role, lined-up position, hit/hurry/sack, beaten, allowed flags, blocked player and block type. Plays without a snap event are excluded from this table.
- Pressure (PFF): a play has pressure when any pass rusher has `pff_hit`, `pff_hurry` or `pff_sack` = 1. In the data, 3,216 of 8,557 plays (37.6%). This is PFF's charting, not a computed measure.
- `player_summary`: counts of plays, games and PFF outcomes by role. Always read together with `n_plays`: 217 players have fewer than 10 plays, and the maximum is 338.
- `team_summary`: per team and side, counts by `passResult`, pressure plays, averages of time to throw, play result and yards to go. Each team has 7 or 8 games in the sample.

## Assumptions and limits
- Only pass plays from weeks 1-8 of 2021 exist. Run plays, special teams and later weeks are absent, so team and player rates describe this sample, not a season.
- Missing participation in a play is not evidence of injury or substitution. Nothing in the data supports either.
- `a` is signed in the source; its direction in space is not provided.
- PFF flags are scouting labels. Do not read hits, hurries or beaten blocks as the causal effect of one player.
- Standardization assumes `absoluteYardlineNumber` is in the raw frame. The check that the QB is behind the line at the snap in 8,532 of 8,533 plays after flipping supports this.
