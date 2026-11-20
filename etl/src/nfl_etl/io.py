"""File helpers: typed CSV reading, atomic writes, hashing."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import polars as pl

from .quality import QualityLog, SchemaError

NULL_TOKENS = ["NA"]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig") as fh:
        line = fh.readline().strip()
    return [c.strip().strip('"') for c in line.split(",")]


def read_csv_typed(path: Path, schema: dict[str, pl.DataType], log: QualityLog,
                   source: str) -> pl.DataFrame:
    """Read a CSV with the expected schema.

    - Missing required columns raise SchemaError. Extra columns are logged and dropped.
    - Fast path: Polars parses with the expected dtypes.
    - Fallback: read as strings and cast; values that fail to cast become null and are logged.
    """
    if not path.exists():
        raise SchemaError(f"{source}: file not found: {path}")
    header = csv_header(path)
    missing = [c for c in schema if c not in header]
    if missing:
        raise SchemaError(f"{source}: missing required columns {missing}")
    extra = [c for c in header if c not in schema]
    log.check(f"{source}.extra_columns", len(extra), detail=f"ignored: {extra}")
    cols = list(schema)
    try:
        return pl.read_csv(path, columns=cols, schema_overrides=schema,
                           null_values=NULL_TOKENS, infer_schema=False, encoding="utf8")
    except pl.exceptions.PolarsError:
        raw = pl.read_csv(path, columns=cols, infer_schema=False, null_values=NULL_TOKENS)
        out = raw.with_columns([pl.col(c).cast(t, strict=False) for c, t in schema.items()])
        for c in cols:
            bad = out[c].is_null().sum() - raw[c].is_null().sum()
            log.check(f"{source}.type_coercion.{c}", bad, detail="value failed cast; set to null",
                      total=raw.height)
        return out.select(cols)


def write_parquet_atomic(df: pl.DataFrame, path: Path) -> None:
    """Write zstd Parquet via a temp file + rename, so partial files never appear."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.write_parquet(tmp, compression="zstd", compression_level=6, statistics=True,
                     row_group_size=262_144)
    os.replace(tmp, path)


def write_json_atomic(obj: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)
