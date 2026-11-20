"""DuckDB catalog: in-memory views over the processed Parquet files (no .duckdb file to go stale)."""
from __future__ import annotations

import glob

import duckdb
import polars as pl

from .config import Paths

# view name -> glob relative to data/processed
VIEWS = {
    "games": "dim/games.parquet",
    "plays": "dim/plays.parquet",
    "players": "dim/players.parquet",
    "pff": "dim/pff.parquet",
    "tracking": "tracking/*/*.parquet",  # hive partition `week=N` becomes a column
    "play_meta": "play_meta/*.parquet",
    "events": "events/events.parquet",
    "play_summary": "agg/play_summary.parquet",
    "player_play": "agg/player_play.parquet",
    "player_summary": "agg/player_summary.parquet",
    "team_summary": "agg/team_summary.parquet",
    "game_summary": "agg/game_summary.parquet",
}


def connect(paths: Paths | None = None, *, only: list[str] | None = None) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB connection with a view per existing Parquet dataset."""
    paths = paths or Paths.default()
    con = duckdb.connect(":memory:")
    for name, rel in VIEWS.items():
        if only is not None and name not in only:
            continue
        pattern = paths.processed / rel
        if not glob.glob(pattern.as_posix()):
            continue
        hive = "true" if name == "tracking" else "false"
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{pattern.as_posix()}', "
                    f"hive_partitioning={hive})")
    return con


def query_df(con: duckdb.DuckDBPyConnection, sql: str) -> pl.DataFrame:
    """Run SQL and return a Polars DataFrame (avoids the pyarrow dependency of DuckDB's .pl())."""
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return pl.DataFrame(rows, schema=cols, orient="row", infer_schema_length=None)
