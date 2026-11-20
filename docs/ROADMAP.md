# Accelerated roadmap

The application has moved through Phases 1-4 and local Phase 6 integration. Continue by completing only the missing Phase 5 vertical slices, then perform one final regression/release pass. Existing features do not need to wait for a formal phase gate, but every new slice must preserve the scientific and data restrictions in `.kiro/steering/project.md`.

## Current sequence

| Phase | State | Evidence or remaining work |
|---|---|---|
| 1. Data engineering | Complete | ETL, Parquet, catalog, reports, validator, CLI, 26 tests |
| 2. Analytics API | Complete | FastAPI/DuckDB routes and 6 tests; optional overview, tactics, and comparison routes included |
| 3. Dashboard foundation | Complete | Responsive dark React dashboard, overview, selectors, loading/error states |
| 4. Interactive field | Complete for accelerated scope | Real 10 Hz SVG replay, controls, trails, vectors, events, selection, and distances |
| 5. Advanced analytics | Partial | QB pressure/matchups, player comparison, tactical summaries, and play selection exist; four named slices remain |
| 6. Local integration | Core verified; final browser polish pending | 32 tests, 20/20 ETL validation, dashboard build, and replay API smoke tests pass |

The exact working-tree state, commands, results, and continuation prompt are in `docs/STATUS.md`.

## Phase 1: data engineering (complete)

Delivered in `etl/`: typed source loading, schema/key checks, deterministic transforms, standardized coordinates, QC flags, partitioned Parquet, event/play metadata, DuckDB aggregate views, manifests, reports, validation, CLI, and synthetic tests.

Acceptance recorded: the real 2021 weeks 1-8 sample was processed without dropped tracking rows or failed games; 20/20 output checks and 26 ETL tests passed in the known baseline.

## Phase 2: analytics API (complete)

Delivered in `backend/main.py`, `backend/database.py`, and `backend/tests/`:

- Health and processed-data readiness.
- Games, teams, players, and filtered/paginated plays.
- Real tracking rows for one play.
- Player and team summaries.
- PFF blocker/rusher matchups.
- Optional overview, tactical grouping, and player comparison.
- Bound query parameters, JSON normalization, local CORS, validation, stable pagination, and clear missing-data errors.

Acceptance recorded: six API tests pass against available processed data; OpenAPI is exposed at `/docs`. Measured representative endpoints complete in 0.04-0.18 s on the development machine, including full tracking retrieval for a normal play.

## Phase 3: dashboard foundation (complete)

Delivered in `dashboard/`:

- Responsive dark layout and mobile navigation.
- Team -> game -> play selection.
- Overview metrics, chart, API status, and loading/empty/error states.
- Relative `api/...` requests, Vite `/api` development proxy, and relative production asset base.

Acceptance recorded: TypeScript and the production build pass. The header labels the 2021 weeks 1-8 sample correctly; manual browser/mobile console review remains.

## Phase 4: interactive field (complete for accelerated scope)

Delivered in `dashboard/src/FootballField.tsx`:

- Real player and ball coordinates on an SVG field.
- Source-rate 10 Hz animation with play/pause, restart, speed, and scrub controls.
- Labels, event display, selected-player highlight/details, trails, direction/velocity vectors, and nearest-player distances.

API retrieval is verified for a sack, a no-snap play, and the longest play (203 frames). Manual browser/mobile behavior still needs review. Zoom/pan and generalized proximity overlays are not part of the completed accelerated scope and must not be implied by documentation or demos.

## Phase 5: advanced analytics (partial)

### Implemented

- **QB pressure and matchups:** selected-play PFF blocking assignments and outcomes, plus pressure-oriented summary cards.
- **Player comparison:** two-player selection and comparison using available summary/movement values.
- **Tactical summaries:** formation, coverage, and dropback groupings with play counts and outcome rates.
- **Play selection:** team, game, and play controls drive the active replay and selected-play views.

### Remaining, in order

#### 5A. Spatial heatmaps

Build player/position occupancy or movement-density heatmaps from real tracking coordinates. Provide team/position/play filters, units/binning notes, `n_plays` and `n_games`, and clear observed/derived labels. Add focused metric/API/UI tests and document any new derived field in `docs/DATA_DICTIONARY.md`.

Acceptance: real data renders; filters alter the sample; empty samples are handled; sample counts and derivation are visible; no causal language.

#### 5B. Blocking network graph

Build an interactive blocker-to-rusher network from PFF assignments. Show matchup frequency, hits/hurries/sacks, and sample size. Preserve unmatched PFF references rather than silently discarding them.

Acceptance: graph and accessible tabular fallback agree on counts; filters and empty states work; outcomes are descriptive, not causal.

#### 5C. Scenario explorer

Compare observed plays involving different players or configurations. Keep observed source values, derived summaries, and experimental output visibly separate. Do not generate hypothetical trajectories unless a validated model is later approved, and never label a prediction as tracking.

Acceptance: users can select and compare real scenarios; provenance and sample limitations remain visible; no external sports data enters the result.

#### 5D. Synchronized replay

Add side-by-side replay of two real plays, preferably from the player comparison or scenario view. Synchronize play/pause and speed while retaining each play's actual frame IDs and duration; define behavior when lengths differ.

Acceptance: both plays use real tracking; scrub/play behavior is deterministic; unequal and missing-event plays work; no interpolated path is presented as observed unless explicitly labeled derived.

### Deferred enhancements

Pocket geometry, dedicated rusher trajectories, full play search, position-specific comparison metrics, zoom/pan, and additional proximity overlays may be added only after the four named remaining slices or by explicit rescope. They are not complete today.

## Phase 6: integration and release

Core local integration, error handling, tests, and dashboard build are verified. Repeat this release gate after every remaining Phase 5 slice:

1. Run `python -m pytest etl/tests backend/tests` with the repository virtual environment.
2. Run real-output ETL validation.
3. Run the dashboard production build.
4. Smoke-test API plus dashboard, sack/missing-event/longest plays, mobile layout, and browser console.
5. Verify all UI labels say 2021 where a season is shown.
6. Update `docs/STATUS.md` with exact results and remaining limits.

Final acceptance: a fresh clone can be restored using separately obtained raw data, rebuild Parquet, start both local services with documented commands, pass all current checks, and display known limitations. No Docker or cloud deployment is required.

## Restrictions carried through every item

- Use only the Big Data Bowl 2023 regional source: 2021 weeks 1-8 pass plays.
- Use no external sports data, injury inference, invented values, or causal claims.
- Show sample sizes next to rankings and rates.
- Label observed, derived, and experimental output.
- Never show predictions or hypothetical trajectories as tracking.
- Flag or report invalid/excluded records; never drop them silently.
- Keep raw and generated data out of Git. Restore raw source separately and regenerate Parquet.
- Keep the application local-first, with no Docker or cloud work unless the owner explicitly changes scope.
