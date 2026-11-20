---
inclusion: always
---
# NFL Tracking Analytics: permanent project rules

## Resume protocol

Read this file, then `docs/STATUS.md`, `docs/ROADMAP.md`, and `docs/DATA_DICTIONARY.md`. Inspect `git status --short --branch` before editing and preserve uncommitted work. Do not ask for the original prompt; `docs/STATUS.md` is the portable handoff.

The project is in accelerated continuation: Phases 1-4 are implemented, Phase 5 is partial, and local Phase 6 checks have been exercised. Complete remaining Phase 5 slices in the order recorded in the roadmap, one tested vertical slice at a time. Do not reopen completed phases or start unrelated refactors. Update `docs/STATUS.md` and `docs/ROADMAP.md` after meaningful changes and before stopping. Do not commit unless explicitly asked.

## Purpose and current scope

Build a local-first application for the NFL Big Data Bowl 2023 regional player-tracking data. Current implemented scope includes the ETL/catalog, read-only analytics API, responsive dark dashboard, real 10 Hz SVG play replay, QB pressure/blocking matchups, player comparison, tactical summaries, and play selection.

The following named Phase 5 features are not complete: spatial heatmaps, blocking network graph, scenario explorer, and synchronized two-play replay. Never describe them as implemented. Broader deferred ideas and current caveats are listed in `docs/ROADMAP.md` and `docs/STATUS.md`.

## Data restrictions (hard rules)

- Use only the Big Data Bowl 2023 regional data for the 2021 season, weeks 1-8, pass plays: `games`, `plays`, `players`, `pffScoutingData`, and `tracking_<gameId>`. Source: `https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data`.
- Do not add external sports data, APIs, or invented statistics. Use the verified schemas and definitions in `docs/DATA_DICTIONARY.md`.
- Do not build injury, medical, or career-impact features. Missing participation is not evidence of injury, and missing tracking is not a confirmed substitution.
- Do not make causal claims from correlations or descriptive tracking outcomes.
- Show sample limits, including `n_plays` and where applicable `n_games`, next to every rate or ranking.
- Keep observed, derived, and experimental output visibly labeled. Predictions and hypothetical paths must never be shown as observed tracking.
- Never silently drop invalid records. Retain them with `qc_flags` when possible or record them in the exclusion report.
- Raw source and generated outputs remain local and ignored. Restore source data separately in `data/raw/` and regenerate `data/processed/` Parquet; do not commit either one.

## Actual stack

- Python 3.12.12 in `.venv/`, never system Python.
- Polars 2.1.0, Parquet, and DuckDB 2.0.1 for ETL/querying.
- FastAPI 0.115.14, Pydantic 2.11.7, and Uvicorn 0.34.3 for the API.
- React 18.3.1, TypeScript 5.7.3, Vite 5.4.21, Tailwind CSS 3.4.19, Recharts 3.10.1, and hand-written SVG for the dashboard.
- pytest 8.3.5 and httpx 0.28.1 for tests.
- Node 22.23.1 and npm 10.x.

No Docker or cloud. Do not add dependencies without a concrete need and a decision recorded in `docs/STATUS.md`. Polars, DuckDB, and dashboard visualization packages intentionally go beyond the event template; the owner chose local-only operation.

Keep the event constraints that still apply: `backend/main.py` exposes `app` and `GET /health`; API routes live under `/api/...`; dashboard requests use relative `api/...` paths without a leading slash; Vite uses `base: './'` and proxies `/api` to `localhost:8000`; secrets belong in `.env`, which is never committed.

## Architecture and layout

- `etl/src/nfl_etl/`: source readers, validation, transforms, aggregates, reports, pipeline, and DuckDB catalog.
- `etl/scripts/etl.py`: command-line launcher.
- `etl/tests/`: synthetic ETL tests; real data is not a test fixture.
- `backend/main.py`: FastAPI routes.
- `backend/database.py`: isolated request-local DuckDB connections, pagination, and JSON normalization.
- `backend/tests/`: API integration tests; data-dependent cases skip without generated Parquet.
- `dashboard/src/App.tsx`: responsive application shell, selectors, overview, and view routing.
- `dashboard/src/FootballField.tsx`: tracking normalization and SVG replay.
- `dashboard/src/AnalyticsViews.tsx`: pressure/matchup, comparison, and tactical views.
- `dashboard/src/api.ts`: relative API client and response adapters.
- `data/raw/`, `data/processed/`, `data/reports/`: ignored local source, generated Parquet, and reports.
- `docs/STATUS.md`: current state, exact commands, known results, issues, and next prompt.
- `docs/ROADMAP.md`: completion map and ordered remaining work.

Leave `.hackathon/`, `.venv/`, and `.kiro/` in place. Do not treat ignored files present on one machine as portable project state.

## Data and implementation conventions

- ETL command: `.venv/bin/python etl/scripts/etl.py <inspect|run|reprocess|validate|sample|report|query>`.
- Tests: `.venv/bin/python -m pytest etl/tests backend/tests`.
- Dashboard check: `cd dashboard && npm run build`.
- Read processed data through `nfl_etl.catalog.connect()` and `query_df()`. Do not add pyarrow; DuckDB `.pl()` is intentionally unused.
- API queries must remain read-only and parameterized. Preserve clear `422`, `404`, and `503 data_unavailable` behavior.
- Use standardized coordinates (`x_std`, `y_std`, offense toward positive x) for analysis. Keep raw `x`, `y`, `o`, and `dir` unchanged.
- Ball rows use `side='ball'` and null `nflId`.
- Use `frameId` as the 10 Hz clock. The source `time` value has only one-second resolution.
- Direction vectors come from `dir`; do not invent acceleration direction.
- New aggregate metrics require units, derivation, sample fields, focused tests, and an update to `docs/DATA_DICTIONARY.md`.
- Preserve missing values rather than filling them without a documented basis.
- Keep code changes narrow. Fix observed failures before adding another feature.

## Accelerated next action

The current baseline is 32 Python tests passed, 20/20 real-data validation checks, and a passing dashboard build. Reconfirm after code changes, then implement only spatial heatmaps as the next Phase 5 slice. Do not combine that work with the blocking network, scenario explorer, or synchronized replay. The exact copyable continuation prompt is at the end of `docs/STATUS.md`.
