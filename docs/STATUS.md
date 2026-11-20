# Status

**Current phase:** Phase 1 (data engineering) COMPLETE. Phase 2 (Analytics API) not started.
**Last updated:** 2026-11-20

## Phase 1: what exists
| Area | Path |
|---|---|
| ETL package | `etl/src/nfl_etl/` (`config`, `schemas`, `io`, `quality`, `dims`, `tracking`, `aggregates`, `catalog`, `pipeline`, `report`, `validate`, `cli`) |
| Launcher | `etl/scripts/etl.py` |
| Tests (synthetic data only) | `etl/tests/` (`synthetic.py`, `conftest.py`, `test_dims_and_tracking.py`, `test_pipeline_cli.py`) |
| Dependencies | `etl/requirements.txt` (polars 2.1.0, duckdb 2.0.1, pytest 8.3.5), installed in `.venv/` |
| Raw data (git-ignored) | `data/raw/` (moved from `nfl-big-data-bowl-regional-event-data-main/data`; the dataset README is now `docs/BDB_SOURCE_README.md`) |
| Outputs (git-ignored) | `data/processed/` (384 MB), `data/reports/` |
| Docs | `etl/README.md` (commands, troubleshooting), `docs/DATA_DICTIONARY.md`, `docs/ROADMAP.md`, `.kiro/steering/project.md` |

Unchanged on purpose: `backend/main.py` (`/health`), `dashboard/`, `.hackathon/`, `.kiro/steering/rules.md`.
Source data: taken from the workspace archive `nfl-big-data-bowl-regional-event-data-main.zip` (already extracted by the owner). The upstream repo was not downloaded again.

## Completed tasks
- Inspected real files and verified schemas, keys, null tokens, time resolution, direction convention, event semantics.
- Built the ETL: typed CSV reading with schema checks, dimension cleaning and key/FK checks, per-game tracking transform (standardization, derived columns, proximity, QC flags), zstd Parquet partitioned by week with one file per game, DuckDB aggregates, manifests, reports, validator, CLI.
- Tests, full run, validation, from-scratch rebuild (below).

## Results (real data)
- Full ETL: 122 games, 8,557 plays, 1,679 players, 8,314,178 tracking rows (none dropped), 361,486 frames. 35 s on this machine. 0 failed games.
- `etl.py validate`: 20/20 checks pass. Rebuilt from scratch after deleting `data/processed` and `data/reports`: same result.
- `pytest etl/tests`: 26 passed (4.5 s). Includes byte-identical re-runs, skip of unchanged games, failure isolation, selective reprocessing, corrupted-output detection.
- Not run: `sh .hackathon/setup.sh --check` (the course checker). Polars and DuckDB are outside its stack list, so it will warn.

## Commands
```sh
.venv/bin/python etl/scripts/etl.py run          # ETL (about 35 s full)
.venv/bin/python etl/scripts/etl.py validate
.venv/bin/python etl/scripts/etl.py sample
.venv/bin/python -m pytest etl/tests
```

## Known issues and decisions
- 29 plays fail `qc_pass`: 24 have no snap event (excluded from `player_play`, so it has 8,533 x 22 rows) and 5 have flagged player rows. They are kept in all tables.
- 59 plays have the ball 3-8 yd from `absoluteYardlineNumber` at the snap; 25 plays cannot be checked (24 without snap, 1 other not investigated). Standardized `x_rel_los` uses `absoluteYardlineNumber` and is less reliable on those plays.
- Ball `dis` has jumps (4,194 rows above 3.5 yd/frame). Flagged, kept. Do not use ball `dis` or ball `a` for analysis without filtering `qc_flags`.
- 953 plays have no pass-forward event (sacks and scrambles, mostly). Time to throw is null for them.
- 2 PFF rows reference a blocked player without a PFF row in the same play.
- `dropBackType` is null in 528 plays, `offenseFormation` in 7. Do not fill them.
- Decision: Float64 for raw and standardized coordinates, Float32 for velocity and distances. Decision: ball flags do not fail `qc_pass`.
- Decision: no pyarrow. DuckDB's `.pl()` needs it, so use `nfl_etl.catalog.query_df`.
- Deployment: processed data is generated locally and git-ignored. An AWS-style ephemeral host would have to rebuild it at start. Out of scope (local-first), revisit in Phase 6 if needed.
- Git: the previous commit on GitHub still contains the raw CSVs under `nfl-big-data-bowl-regional-event-data-main/data` (826 MB). Current changes are uncommitted; committing them removes those files from the tree but not from history.

## Expensive operations (do not repeat)
Full ETL is cheap (35 s). Nothing else is expensive. Do not re-profile the raw CSVs; use `docs/DATA_DICTIONARY.md`.

## Next action
Start Phase 2 when instructed: `backend/app/` with routers under `/api` reading the Parquet through `nfl_etl.catalog.connect()` (add `etl/src` to the backend's import path, or move the catalog helper into a shared package), Pydantic models, and `backend/tests/` with synthetic data. First endpoints: `games`, `teams`, `players`, `plays`, `plays/{gameId}/{playId}/tracking`, then metrics and matchups. See `docs/ROADMAP.md` Phase 2.
