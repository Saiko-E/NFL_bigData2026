# NFL Tracking Analytics

Local-first web app for exploring NFL player tracking data from the Big Data Bowl 2023 regional dataset (2021 season, weeks 1-8, pass plays). Built in phases; the current state is in `docs/STATUS.md`.

| Phase | Status |
|---|---|
| 1. Data engineering (ETL, Parquet, quality reports) | done |
| 2. Analytics API | next |
| 3-6. Dashboard, interactive field, advanced analytics, release | planned (`docs/ROADMAP.md`) |

## Project layout

```
etl/         data pipeline (src/nfl_etl, tests, scripts/etl.py) and its README
backend/     FastAPI app (main.py with /health; the API arrives in Phase 2)
dashboard/   React + TypeScript + Vite frontend
data/        raw/ (input CSVs), processed/ (Parquet), reports/ (quality reports); all git-ignored
docs/        ROADMAP.md, STATUS.md, DATA_DICTIONARY.md
.kiro/       steering files (project.md, rules.md)
.hackathon/  event setup scripts (do not move)
```

## Quick start

Requirements: Python 3.11+ and Node 22 (versions used: `.hackathon/stack.json`).

```sh
# 1. Environment (course installer, creates .venv/)
sh .hackathon/setup.sh
.hackathon/.tools/uv/uv pip install --python .venv/bin/python -r etl/requirements.txt

# 2. Put the dataset files in data/raw/ (see etl/README.md), then build the data
.venv/bin/python etl/scripts/etl.py run          # about 35 s
.venv/bin/python etl/scripts/etl.py validate
.venv/bin/python -m pytest etl/tests

# 3. Existing backend and dashboard shells
.venv/bin/uvicorn backend.main:app --reload       # http://localhost:8000/health
cd dashboard && npm ci && npm run dev
```

Full ETL commands, outputs and troubleshooting: `etl/README.md`. Column definitions and data limits: `docs/DATA_DICTIONARY.md`.

## Data and limits

Only the sample data is used: no external sources and no invented statistics. Results describe pass plays from 8 weeks of 2021, not a full season. Credentials go in `.env` (copy `.env.example`); it is never committed.
