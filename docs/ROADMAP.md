# Roadmap

Order is fixed. Finish a phase (acceptance criteria met and recorded in `STATUS.md`) before starting the next. Credit budget: 900 for the whole project, so keep each phase focused.

Dependencies: Phase 1 -> 2 -> 3 -> 4 -> 5 -> 6. Phase 4 needs the tracking endpoint from Phase 2 and the layout from Phase 3. Phase 5 builds on 2, 3 and 4.

## Phase 1: Data engineering (DONE)
Deliverables: ETL (`etl/`), Parquet outputs, DuckDB catalog, quality reports, CLI, tests, docs.
Acceptance: real files read; full ETL runs without critical errors; Parquet queryable; keys validated; reports exist; tests pass; docs executable. Results in `STATUS.md`.

## Phase 2: Analytics API
Deliverables (`backend/app/`, `backend/tests/`; `backend/main.py` mounts routers under `/api`):
- Endpoints: games, teams, players, plays (filters + pagination), tracking for one play (compact JSON or arrays for 10 Hz replay), events, matchups (PFF blocker vs rusher), computed metrics (play, player, team summaries), data-quality summary, `/health`.
- Pydantic response models; DuckDB over the processed Parquet (read-only); input validation; consistent errors; sample-size fields (`n_plays`, `n_games`) on every aggregate.
Acceptance: pytest with synthetic data passes; every endpoint answers on the real data in under 1 s for play-level queries; OpenAPI docs load; missing processed data returns a clear error.

## Phase 3: Dashboard foundation
Deliverables: responsive layout, navigation for the sections below, global filters (week, team, game, position), API client (`fetch('api/...')`), Overview page (KPIs, rankings with sample size, tables, Plotly charts), loading and error states.
Acceptance: `npm run build` passes (typecheck included); Overview shows real API data; filters change results; no console errors.

## Phase 4: Interactive field
Deliverables: SVG/D3 field with players and ball from real tracking (10 Hz): play/pause, speed control, timeline scrubber, events markers, player selection and highlight, trails, velocity and orientation vectors (direction vector from `dir`; no acceleration direction is available), player-to-player and QB distances, zoom/pan, proximity overlays.
Acceptance: smooth playback of a full play; frame shown equals the data frame; works on a sack play and a play with a missing event; performance check on the longest play (203 frames).

## Phase 5: Advanced analytics
Deliverables, each with sample sizes and a short "how to read" note:
- C. QB pressure: rusher trajectories, QB-defender distance, blocking assignments and matchups, PFF sacks/hits/hurries, approximate pocket geometry (derived, labeled as approximate).
- D. Player comparison: same-position players, speed/acceleration/movement/participation, position-specific metrics, synchronized replay of two real plays, rankings with minimum-sample filter.
- E. Spatial: player and position heatmaps, movement density, defensive positioning.
- F. Tactical: formations and personnel, coverage, play-action and dropback, trends by team and situation.
- G. Blocking network: blockers vs defenders, PFF assignments, matchup frequency and outcomes, interactive graph.
- H. Play explorer: search/filter by team, player, formation, coverage, event, outcome; notable observed plays; replay.
- I. Scenario explorer: compare real plays involving different players or configurations; observed / derived / experimental kept separate. Hypothetical trajectories only after a validated model, always labeled as not tracking.
Acceptance: each view works on real data; derived metrics documented in `DATA_DICTIONARY.md`; no causal wording; tests for metric functions.

## Phase 6: Integration and release
Deliverables: end-to-end tests, performance pass (cache/pre-aggregation where needed), error handling, UI polish, one-command local start, final docs (README with screenshots), `STATUS.md` closed out.
Acceptance: fresh clone + documented setup runs the app; all tests pass; known limitations listed.

## Requirements carried from the project brief
- Features A-I above. Observed vs derived vs experimental stays visible in the UI.
- Scientific constraints in `.kiro/steering/project.md` apply to every phase.
- Local-first, no Docker/cloud, Python dependencies kept minimal.
