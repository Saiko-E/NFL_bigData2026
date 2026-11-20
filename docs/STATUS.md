# Project status and portable handoff

**Updated:** 2026-11-20

**State:** Phases 1-4 are implemented. Phase 5 is partial. Phase 6 local integration is verified: 32 Python tests, 20/20 real-data checks, production dashboard build, and targeted replay/API smoke tests pass.

**Git:** branch `main`; implementation commit `978a080` (`Build NFL tracking analytics API and dashboard`) was pushed to `origin/main`. A later documentation-only handoff commit may be `HEAD`; use `git log -1 --oneline` to confirm the clone's exact current commit.

## Purpose and architecture

NFL Tracking Analytics is a local-first application for exploring the NFL Big Data Bowl 2023 regional dataset: 2021 season, weeks 1-8, pass plays only. It uses no external sports feeds and does not invent missing statistics.

The data flow is:

1. `etl/` validates source CSVs and writes partitioned Parquet plus quality reports.
2. `backend/main.py` exposes a read-only FastAPI service. `backend/database.py` opens an isolated in-memory DuckDB catalog over Parquet for each request; there is no persistent database file.
3. `dashboard/` is a responsive dark React application. Vite proxies relative `api/...` calls to the local API.
4. `dashboard/src/FootballField.tsx` normalizes row or frame responses and renders real standardized tracking coordinates (`x_std`, `y_std`, offense toward +x) in an SVG at the source 10 Hz cadence.

Processed data stays local. A fresh clone does not contain raw CSVs, generated Parquet, reports, virtual environments, dependencies, or dashboard builds.

## Completion by phase

### Phase 1: complete

- Typed CSV inspection and loading, schema checks, key and foreign-key validation, deterministic per-game transforms, coordinate standardization, proximity fields, QC flags, failure isolation, and incremental rebuild manifests.
- Zstandard Parquet partitioned by week/game, DuckDB catalog views, aggregate tables, event/play metadata, quality reports, validator, CLI, and synthetic tests.
- Real-data result from the completed run: 122 games, 8,557 plays, 1,679 players, 8,314,178 tracking rows, and 361,486 frames; no tracking rows dropped and no game failed.
- Real-output validation previously passed 20/20 checks. A from-scratch rebuild produced the same result.

### Phase 2: complete

- FastAPI application in `backend/main.py` and query helpers in `backend/database.py`.
- Required routes: `/health`, `/api/health`, `/api/games`, `/api/teams`, `/api/players`, `/api/plays`, `/api/plays/{gameId}/{playId}/tracking`, `/api/players/{nflId}/stats`, `/api/teams/{team}/stats`, and `/api/plays/{gameId}/{playId}/matchups`.
- Optional implemented routes: `/api/overview`, `/api/analytics/tactics`, and `/api/players/compare`.
- Filtering, stable pagination, bound DuckDB parameters, local CORS, JSON-safe date/time and non-finite values, `422` validation, `404` missing-record responses, and clear `503 data_unavailable` responses.
- Six API tests cover health/CORS, missing data, real catalog totals, filters/pagination, tracking/matchups/stats, optional analytics, and validation errors. Data-dependent tests skip if processed Parquet is absent.

### Phase 3: complete

- Responsive dark dashboard with desktop/mobile navigation, loading/empty/error states, API status, overview metrics and chart, and team -> game -> play selectors.
- Relative API client and Vite `/api` proxy; portable `base: './'` production assets.
- GitHub Pages deployment in `.github/workflows/pages.yml`; because Pages is static, `dashboard/public/demo.json` contains one real observed play (43 frames / 989 tracking rows), 54 player summaries, five PFF matchups, and actual tactical aggregates. The full local app still requires FastAPI and the ignored processed data.

### Phase 4: complete for the accelerated scope

- Real SVG field and football/player locations from the selected play's tracking response.
- 10 Hz playback using animation frames, play/pause, restart, 0.5x-2x speed, and timeline scrubbing.
- Labels, selected-player highlight and details, selected-player trail, direction/velocity vectors, current event display, and nearest-player distances.
- No synthetic trajectories are displayed as observed tracking.

### Phase 5: partial

Implemented:

- QB pressure and blocker/rusher matchup assignments and outcomes for the selected play.
- Two-player comparison with available tracking-derived summary metrics.
- Tactical summaries by formation, coverage, or dropback.
- Team, game, and play selection feeding the replay and analysis views.

Not implemented and not to be presented as complete:

- Spatial heatmaps.
- Blocking network graph.
- Scenario explorer.
- Synchronized two-play replay.

The broader Phase 5 ideas such as pocket geometry, dedicated rusher trajectory analysis, richer search/filtering, and position-specific comparison metrics also remain future work unless explicitly rescoped.

### Phase 6: local integration performed

- API/dashboard local flow is wired, and missing-data and UI error states exist.
- Verified current result: 26 ETL tests plus 6 backend tests, 32 passed.
- Verified current result: ETL real-output validation passed 20/20 checks.
- Verified current result: `npm run build` passes, including TypeScript checking.
- Targeted API smoke tests passed for a normal play, longest play (203 frames / 4,669 rows), no-snap play, and sack play; all rows were returned.
- No cloud or Docker deployment is planned. Fresh-clone restoration still requires obtaining the raw dataset separately and rebuilding Parquet.

## Pending work, in execution order

1. **Implement spatial heatmaps:** observed player/position occupancy or movement density, with filters, sample counts, units, and documented derivation.
2. **Implement the blocking network graph:** build it from PFF blocker-to-rusher assignments; expose sample size and outcomes without causal claims.
3. **Implement the scenario explorer:** compare real observed plays/configurations. Keep observed, derived, and experimental content visibly separate; do not show generated paths as tracking.
4. **Implement synchronized replay:** two real plays with shared play/pause, speed, and timeline behavior, while retaining each play's own frame identity.
5. **Finish browser release checks:** check mobile layout and browser console behavior, then repeat automated checks after any remaining feature work.

Do not expand these items into unrelated refactors. Finish one vertical feature at a time and validate it before moving to the next.

## Important paths

| Path | Role |
|---|---|
| `README.md` | Four-line entry point |
| `.kiro/steering/project.md` | Permanent restrictions, stack, and resume protocol |
| `docs/STATUS.md` | Current portable handoff and next action |
| `docs/ROADMAP.md` | Actual phase state and remaining acceptance criteria |
| `docs/DATA_DICTIONARY.md` | Source columns, derived metrics, QC, and data limits |
| `docs/BDB_SOURCE_README.md` | Preserved source-dataset README |
| `etl/src/nfl_etl/` | ETL package and DuckDB catalog |
| `etl/scripts/etl.py` | ETL CLI launcher |
| `etl/tests/` | 26 synthetic ETL tests |
| `etl/README.md` | Raw layout, ETL commands, outputs, and troubleshooting |
| `backend/main.py` | FastAPI app and routes |
| `backend/database.py` | Request-safe DuckDB query and JSON helpers |
| `backend/tests/` | 6 API integration tests |
| `backend/README.md` | API routes and service notes |
| `dashboard/src/App.tsx` | Layout, selectors, overview, and view routing |
| `dashboard/src/FootballField.tsx` | Tracking normalization and SVG replay |
| `dashboard/src/AnalyticsViews.tsx` | Matchup, comparison, and tactical views |
| `dashboard/src/api.ts` | Relative API client and response adapters |
| `dashboard/vite.config.ts` | Relative build base and local API proxy |
| `dashboard/README.md` | Dashboard run/build notes and GitHub Pages demo link |
| `dashboard/public/demo.json` | Small committed real-data snapshot for static GitHub Pages only |
| `.github/workflows/pages.yml` | Builds and deploys the static dashboard demo |
| `data/raw/` | Restored source CSVs; ignored |
| `data/processed/` | Generated Parquet; ignored |
| `data/reports/` | Generated quality reports; ignored |

## Toolchain and pinned versions

- Python 3.12.12, uv 0.11.19, Node 22.23.1, npm 10.x from `.hackathon/stack.json`.
- API/test pins in `.hackathon/requirements.txt`: FastAPI 0.115.14, Uvicorn 0.34.3, Pydantic 2.11.7, httpx 0.28.1, pytest 8.3.5.
- ETL pins in `etl/requirements.txt`: Polars 2.1.0, DuckDB 2.0.1, pytest 8.3.5.
- Dashboard pins in `dashboard/package.json`: React/React DOM 18.3.1, Recharts 3.10.1, TypeScript 5.7.3, Vite 5.4.21, Tailwind CSS 3.4.19.
- The project intentionally adds Polars, DuckDB, Recharts, and the custom SVG visualization beyond the original event template. It remains local-only.

## Restore, install, and rebuild from a fresh clone

Run commands from the repository root. Do not use system Python for project commands.

```sh
# Create/update the repository-local event environment.
sh .hackathon/setup.sh

# Add the ETL dependencies to that environment.
.hackathon/.tools/uv/uv pip install --python .venv/bin/python -r etl/requirements.txt

# Install the exact dashboard dependency tree.
cd dashboard
npm ci
cd ..
```

Restore the raw source separately. Obtain the `data/` files from the Big Data Bowl regional source repository or the owner's matching archive, then place them in this exact ignored layout:

```text
data/raw/games.csv
data/raw/plays.csv
data/raw/players.csv
data/raw/pffScoutingData.csv
data/raw/tracking/tracking_<gameId>.csv   # 122 game files for this dataset
```

Source: `https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data`. Do not commit the raw files. After restoration, rebuild and validate Parquet instead of copying generated outputs from another machine:

```sh
.venv/bin/python etl/scripts/etl.py inspect
.venv/bin/python etl/scripts/etl.py run --force
.venv/bin/python etl/scripts/etl.py validate
```

`NFL_DATA_DIR=/path/to/data` or `--data-dir PATH` may point the ETL/API at a different data root. This is the only place where a machine-specific path should be supplied by the operator.

## Run locally

Use separate terminals from the repository root:

```sh
# Terminal 1: API
.venv/bin/uvicorn backend.main:app --reload

# Terminal 2: dashboard
cd dashboard
npm run dev
```

Local URLs:

- Dashboard development: `http://localhost:5173/` (or the next port printed by Vite if 5173 is occupied).
- Single-port production preview: run `cd dashboard && npm run build`, return to the repository root, then start Uvicorn; FastAPI serves the built dashboard at `http://localhost:8000/`.
- API health: `http://localhost:8000/health` and `http://localhost:8000/api/health`.
- OpenAPI UI: `http://localhost:8000/docs`.
- OpenAPI JSON: `http://localhost:8000/openapi.json`.

## Validation commands and known results

```sh
# ETL tests: 26 passed (verified current tree)
.venv/bin/python -m pytest etl/tests

# Backend tests: 6 passed with processed data (verified current tree)
.venv/bin/python -m pytest backend/tests

# Combined regression: 32 passed (verified current tree)
.venv/bin/python -m pytest etl/tests backend/tests

# Validate current real Parquet outputs: 20/20 checks passed
.venv/bin/python etl/scripts/etl.py validate

# Typecheck and production dashboard build: passed
cd dashboard && npm run build
```

The course checker was not part of the known results. `sh .hackathon/setup.sh --check` is expected to warn about intentional dependencies outside the event stack.

## Data limits, decisions, and known issues

- The sample contains 2021 weeks 1-8 pass plays, not a full season. Every rate or ranking must show `n_plays` and, where applicable, `n_games`.
- Only `games`, `plays`, `players`, `pffScoutingData`, and per-game tracking files from the stated source are permitted. No external sports data or invented values.
- Label output as observed, derived, or experimental. Avoid causal wording. Predictions or hypothetical trajectories must never appear as observed tracking.
- No injury, medical, or career-impact features. Missing participation does not establish injury or substitution.
- Keep invalid rows with QC flags when possible and log exclusions; never drop them silently.
- Raw `x`, `y`, `o`, and `dir` are preserved. Analysis uses `x_std`, `y_std`, where offense moves toward positive x. `frameId`, not the one-second-resolution `time`, is the 10 Hz clock.
- Float64 is used for raw/standardized coordinates; Float32 is used for velocity and distance fields. Ball flags do not fail play-level `qc_pass`.
- Do not add pyarrow. DuckDB `.pl()` requires it; use `nfl_etl.catalog.query_df()` instead.
- Twenty-nine plays fail `qc_pass`: 24 lack a snap event and 5 have flagged player rows. They remain in the data; the 24 no-snap plays are excluded from `player_play`.
- Fifty-nine plays place the ball 3-8 yards from `absoluteYardlineNumber` at snap; another 25 cannot be checked. Treat `x_rel_los` cautiously on these plays.
- Ball `dis` has 4,194 rows above 3.5 yards/frame. Filter `qc_flags` before using ball `dis` or ball acceleration.
- Nine hundred fifty-three plays have no pass-forward event, mostly sacks and scrambles, so time to throw is null.
- Two PFF blocked-player references have no matching PFF player row in the same play.
- `dropBackType` is null in 528 plays and `offenseFormation` in 7; do not fill these values.
- The dashboard header correctly labels the sample as 2021 weeks 1-8.
- The tactical dashboard currently requests dataset-wide formation summaries. The endpoint can instead group by coverage or dropback and filter by team/week; game/play-specific tactical summaries are not implemented.
- Processed data is generated and local. Deployment to an ephemeral host would require source restoration and ETL at startup and remains out of scope.

## Event submission mode

The event's `--entregar` checker was rerun successfully on the current tree. Result: 185 archive entries, 171.3 MB, fixed event stack, dashboard build, backend import, routes, README visual, credentials scan, and ZIP integrity all passed without warnings. Upload `../entrega-hackathon-unam-20261120-1237.zip`; do not upload the earlier 722.2 MB archive.

To prevent duplicated generated data in submissions while keeping the complete local app usable, `data/processed` and `data/reports` are local symbolic links to sibling storage under `../hackathon-unam-local-data/`; `data/raw` remains a real directory and its 126 source files remain in the event ZIP. The redundant source archive was moved to `../nfl-big-data-bowl-regional-event-data-main.zip`. None of these local storage locations are committed.

The repository `.venv` currently contains exactly the event stack. DuckDB and Polars were removed only from the environment, not from source or lock files. In this mode FastAPI imports successfully, `/health` returns `status=ok` with `mode=static-demo`, and the built dashboard falls back to the bundled real play in `dashboard/public/demo.json` when full analytics return `503`.

After submitting, restore full local analytics with:

```sh
.hackathon/.tools/uv/uv pip install --python .venv/bin/python -r etl/requirements.txt
```

Before generating another warning-free event ZIP, remove the optional packages again:

```sh
.hackathon/.tools/uv/uv pip uninstall --python .venv/bin/python duckdb polars polars-runtime-32
sh .hackathon/setup.sh --entregar
```

## Ignored and regenerated content

`.gitignore` excludes `.venv/`, `.hackathon/.tools/`, `.hackathon/.cache/`, `.hackathon/.bootstrap/`, `node_modules/`, `dist/`, `dashboard/dist/`, Python caches, pytest/ruff caches, logs, delivery ZIPs, `.env*` except `.env.example`, keys, `.aws/`, DuckDB files/WALs, and all of `data/raw/`, `data/processed/`, and `data/reports/`.

Never use ignored local presence as proof that another clone can run. Restore source data separately, reinstall dependencies, and rebuild Parquet as described above.

## Next task

Implement **spatial heatmaps** as the next missing Phase 5 vertical slice. Use only observed tracking or clearly documented derived bins, expose sample size and filters, add focused tests, update `docs/DATA_DICTIONARY.md` if a metric is introduced, and update this status before stopping.

## Copyable continuation prompt

```text
Resume NFL Tracking Analytics from the repository root. Read .kiro/steering/project.md, docs/STATUS.md, docs/ROADMAP.md, and docs/DATA_DICTIONARY.md; inspect git status before editing and preserve all existing uncommitted work. The current baseline is 32 Python tests passed, 20/20 ETL validation checks, and a passing dashboard build. Confirm it only if code has changed, then implement only the next missing Phase 5 slice: spatial heatmaps from the allowed 2021 weeks 1-8 pass-play tracking data. Show sample sizes and filters, label observed versus derived values, add focused tests, use relative api/... requests, and do not add external data, Docker, cloud services, injury claims, causal claims, invented statistics, or hypothetical paths presented as tracking. Do not start the blocking network, scenario explorer, or synchronized replay in the same slice. Update STATUS and ROADMAP before stopping; do not commit unless explicitly asked.
```
