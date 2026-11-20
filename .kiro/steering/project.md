---
inclusion: always
---
# NFL Tracking Analytics: permanent project rules

**Resume protocol:** read this file, then `docs/ROADMAP.md` and `docs/STATUS.md`. Do not ask for the original prompt. Update `docs/STATUS.md` after meaningful changes and before stopping. Work one phase at a time; never start the next phase without instruction.

## Purpose
Local-first web app for exploring NFL player-tracking data: overview, interactive field replay (10 Hz), QB pressure, player comparison, spatial and tactical analytics, blocking matchup network, play explorer, scenario explorer. Feature list: `docs/ROADMAP.md`.

## Data restrictions (hard rules)
- Only the Big Data Bowl 2023 regional data (season 2021, weeks 1-8, pass plays): `games`, `plays`, `players`, `pffScoutingData`, `tracking_<gameId>`. Source: github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data.
- No external sports data, APIs or invented statistics. Verified schemas: `docs/DATA_DICTIONARY.md`.
- No injury, medical or career-impact features. Missing participation is not an injury. Do not claim confirmed substitutions. No causal claims from correlations.
- State sample limits (n plays, n games) next to every ranking or rate. Label views as observed, derived, or experimental. Predictions are never shown as tracking.
- Never drop invalid records silently: flag them (`qc_flags`) or log them in the exclusion report.

## Stack
Python 3.12 in `.venv/` (never system Python), Polars + Parquet + DuckDB, FastAPI + Pydantic, React 18 + TypeScript + Vite 5 + Tailwind 3, D3/SVG for the field, Plotly for charts, pytest. No Docker or cloud. No new dependencies without a reason recorded in `docs/STATUS.md`.
Deviation: Polars, DuckDB, Plotly and D3 are outside the event stack in `.kiro/steering/rules.md`. The owner chose this knowingly (AWS will not host it). Keep the parts of `rules.md` that still apply: `backend/main.py` exposes `app` with `GET /health`; API under `/api/...`; dashboard calls `fetch('api/...')` without a leading slash; Vite `base: './'` and a dev proxy of `/api` to `localhost:8000`; no keys in code; `.env` is never committed.

## Layout
`etl/` (pipeline: `src/nfl_etl`, `tests`, `scripts/etl.py`), `backend/` (FastAPI; Phase 2 adds `app/` and `tests/`), `dashboard/` (frontend), `data/raw|processed|reports` (git-ignored), `docs/`, `.kiro/steering/`. Leave `.hackathon/`, `.venv/`, `.kiro/` in place.

## Conventions
- ETL commands: `.venv/bin/python etl/scripts/etl.py <inspect|run|reprocess|validate|sample|report|query>`. Tests: `.venv/bin/python -m pytest etl/tests` (synthetic fixtures only; real data is never used in tests).
- Read processed data through `nfl_etl.catalog.connect()` (DuckDB views over Parquet) and `query_df()`. Do not add pyarrow.
- Use standardized coordinates (`x_std`, `y_std`: offense moves toward +x) for analysis. Raw `x`, `y`, `o`, `dir` stay unchanged in the output.
- Ball rows have `side='ball'` and null `nflId`. Frame number (`frameId`) is the 10 Hz clock; `time` only has 1 s resolution.
- Keep code small and tested. Fix real errors before adding features. Prefer targeted file reads over dumping data.
