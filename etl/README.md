# ETL: NFL tracking data (Big Data Bowl 2023 regional data)

Turns the raw CSVs in `data/raw/` into validated, partitioned Parquet in `data/processed/`, plus quality reports in `data/reports/`. Measured on this project's data (8.3 M tracking rows, 122 games): about 35 s for a full run, 373 MB of tracking Parquet.

All commands run from the project root.

## 1. Install (user-writable, inside the project)

With the course installer (creates `.venv/` with the event stack):

```sh
sh .hackathon/setup.sh
.hackathon/.tools/uv/uv pip install --python .venv/bin/python -r etl/requirements.txt
```

Without it (Python 3.11+):

```sh
python3 -m venv .venv
.venv/bin/pip install -r etl/requirements.txt
```

`etl/requirements.txt` pins `polars`, `duckdb` and `pytest`. No system Python is touched.

## 2. Put the raw data in place

Copy the files of the source repository's `data/` folder (https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data) to `data/raw/`:

```
data/raw/games.csv
data/raw/plays.csv
data/raw/players.csv
data/raw/pffScoutingData.csv
data/raw/tracking/tracking_<gameId>.csv     (122 files)
```

Raw files are never modified. `data/raw`, `data/processed` and `data/reports` are git-ignored.

## 3. Commands

```sh
ETL=".venv/bin/python etl/scripts/etl.py"
$ETL inspect              # compare CSV headers/row counts with the expected schemas (-v lists every column)
$ETL run                  # full ETL; skips games whose inputs did not change
$ETL run --limit 3        # smoke test on the first 3 games
$ETL run --games 2021090900 2021091200      # only these games
$ETL run --force          # rebuild everything
$ETL reprocess 2021090900 # force-reprocess selected games, then rebuild aggregates and reports
$ETL validate             # independent checks on the outputs (exit code 1 on a critical failure)
$ETL sample               # one play: events, QB/ball track, PFF rush vs block (--game G --play P to choose)
$ETL query "select week, count(*) from plays group by 1 order by 1"
$ETL report               # regenerate the reports from existing manifests
```

Exit codes: `0` ok, `1` some game failed or a validation check failed, `2` a source file does not match the expected schema (nothing is written).
Use another data directory with `--data-dir PATH` or `NFL_DATA_DIR`.

## 4. Outputs

```
data/processed/
  dim/            games, plays, players, pff (.parquet)
  tracking/week=W/part-<gameId>.parquet     one file per game, sorted by play, frame, entity
  play_meta/<gameId>.parquet                per-play tracking QC and event frames
  events/events.parquet
  agg/            play_summary, player_play, player_summary, team_summary, game_summary
  _manifest/      per-game JSON (input hash, counts, checks, exclusions) used to skip unchanged games
data/reports/
  quality_report.md|json   totals, records per source/table, checks, failed/skipped files, exclusions
  exclusions_detail.json   example keys of every excluded row
  validation.json          result of `validate`
```

Column and metric definitions: `docs/DATA_DICTIONARY.md`.

Query from Python (DuckDB views over the Parquet files, no database file):

```python
from nfl_etl.catalog import connect, query_df   # run with PYTHONPATH=etl/src
con = connect()
query_df(con, "SELECT team, side, n_plays, n_pressure_plays FROM team_summary ORDER BY team")
```

## 5. What the pipeline guarantees

- Required columns and types are checked. A missing column stops the run before anything is written. Values that fail a type cast become null and are counted.
- Rows are dropped only for: wrong `gameId` in a file, null `playId`/`frameId`, a non-ball row without `nflId`, a repeated key, or a `playId` absent from `plays.csv`. Each drop is logged with its rule and example keys. On the real data none were dropped.
- Out-of-range positions, speeds, accelerations and distances are flagged in `qc_flags` and kept.
- Football rows keep a null `nflId` and get `side='ball'`.
- Raw `x`, `y`, `o`, `dir` are preserved; standardized columns are added so the offense always moves toward +x.
- Each game is processed alone (about 90 k rows), written atomically (temp file, then rename). Distance joins stay within one play and frame. A failing game is recorded in its manifest and the run continues.
- Re-runs are deterministic (identical Parquet bytes, tested) and skip unchanged games.

## 6. Tests and validation

```sh
.venv/bin/python -m pytest etl/tests      # 26 tests on SYNTHETIC data generated in temp dirs (never the real data)
.venv/bin/python etl/scripts/etl.py validate   # 20 checks on the real outputs
```

`validate` re-derives its results from the Parquet files: key uniqueness, foreign keys, ball/nflId rule, frame contiguity, sort order, standardization (QB behind the line at the snap in over 99.9% of plays), value ranges, `dis` vs position change, compression, and consistency between tables.

## 7. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `SCHEMA ERROR: ... missing required columns` | A CSV header changed or the wrong file is in `data/raw`. Run `inspect -v`. |
| `file not found: .../games.csv` | Raw data not in `data/raw/`. See section 2. |
| Game `FAILED` in the run log | See `data/processed/_manifest/game_<id>.json` (`error`, `trace`). Fix the file, run again; failed games are always retried. |
| `validate` says `outputs_exist` failed | Run `run` first, or the run stopped before aggregates. |
| Nothing happens on `run` | All games unchanged. Use `--force` or `reprocess <id>`. |
| `ModuleNotFoundError: nfl_etl` in a script | Use `etl/scripts/etl.py`, or set `PYTHONPATH=etl/src`. |
| `module 'duckdb' ... .pl()` needs pyarrow | Use `query_df(con, sql)` instead of `.pl()`; pyarrow is not installed on purpose. |
| `Resource In Use` from DuckDB | A previous `execute().fetchone()` was left open. Use `fetchall()`. |
