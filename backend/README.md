# Phase 2 API

Read-only FastAPI service over the Parquet views defined by `etl/src/nfl_etl/catalog.py`. It opens an isolated in-memory DuckDB catalog per request, so concurrent requests do not share connection state and no database file can become stale.

The service has two explicit modes:

- **Full analytics:** install `etl/requirements.txt` and provide `data/processed`; all API endpoints query the complete dataset.
- **Event/static demo:** with only the event's fixed Python stack, `/health` stays healthy, FastAPI serves `dashboard/dist`, and unavailable analytics endpoints return `503`. The dashboard then loads the bundled real-data snapshot from `dashboard/public/demo.json`.

## Run

From the repository root:

```bash
.venv/bin/uvicorn backend.main:app --reload
```

The API uses `NFL_DATA_DIR` through the ETL `Paths` configuration when set. Otherwise it reads `data/processed`. OpenAPI documentation is available at `http://localhost:8000/docs`.

## Endpoints

- `GET /health`, `GET /api/health`: service and processed-data availability
- `GET /api/overview`: dataset totals and headline metrics
- `GET /api/games`: filters `week`, `season`, `team`
- `GET /api/teams`: filter `search`
- `GET /api/players`: filters `search`, `position`, `team`
- `GET /api/plays`: filters `gameId`, `week`, `team`, `formation`, `passResult`, `hasPressure`
- `GET /api/plays/{gameId}/{playId}/tracking`: filters `frameStart`, `frameEnd`, `nflId`, `side`; maximum `limit` is 10,000
- `GET /api/players/{nflId}/stats`
- `GET /api/teams/{team}/stats`
- `GET /api/plays/{gameId}/{playId}/matchups`: PFF blocker-to-rusher assignments and outcomes
- `GET /api/analytics/tactics`: grouped by `formation`, `coverage`, or `dropback`; filters `team`, `week`, `minPlays`
- `GET /api/players/compare?nflIds=25511,35466`: compare 2–10 players

List endpoints accept `limit` and `offset` and return:

```json
{"items": [], "total": 0, "limit": 100, "offset": 0}
```

Invalid parameters return FastAPI `422` responses, missing records return `404`, and unavailable processed datasets return `503` with code `data_unavailable`. Query values are bound as DuckDB parameters. Dates, times, timestamps, NaN, and infinity are normalized to strict JSON values. Browser CORS is enabled for `localhost` and `127.0.0.1` on any port.

## Test

```bash
.venv/bin/python -m pytest backend/tests
```

Tests use the real processed dataset when present. Data-dependent tests skip when `data/processed/dim/games.parquet` is absent; health and CORS coverage still run. If `dashboard/dist` exists, FastAPI also serves that production build at `/`.
