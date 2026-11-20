# NextDown NFL Analytics Dashboard

Dark, responsive React dashboard for exploring NFL tracking data and analytics.

## Run locally

Install once on a fresh clone, then start Vite:

```bash
cd dashboard
npm ci
npm run dev
```

Vite serves the UI and proxies `/api` requests to `http://localhost:8000`. Start the API on port 8000 before selecting a game. Production assets use `base: './'`, so the build remains portable.

## Build

```bash
npm run build
```

The static output is written to `dashboard/dist`. If this directory exists when FastAPI starts, the backend also serves the dashboard at `http://localhost:8000/`; build first, then restart Uvicorn for single-port use.

## Data flow

1. Select a team, then a game, then a play.
2. The field requests `api/plays/{gameId}/{playId}/tracking`.
3. Tracking responses may contain row-per-player records or nested frame objects. The client normalizes both forms and plays frames at 10 Hz.
4. Select a player on the field to inspect speed, direction, position, trails, and distances to nearby players.

## API routes

- `GET /api/overview`
- `GET /api/teams`
- `GET /api/games?team=...`
- `GET /api/players?team=...`
- `GET /api/plays?gameId=...`
- `GET /api/plays/{gameId}/{playId}/tracking`
- `GET /api/plays/{gameId}/{playId}/matchups`
- `GET /api/players/{id}/stats`
- `GET /api/players/compare?nflIds=...`
- `GET /api/analytics/tactics?dimension=formation|coverage|dropback`

The adapters accept common camelCase and snake_case NFL field aliases, and list responses can be raw arrays or nested under keys such as `data`, `results`, `teams`, `games`, `plays`, or `frames`.
