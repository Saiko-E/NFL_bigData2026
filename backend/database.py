"""Small query layer over the ETL's in-memory DuckDB catalog."""
from __future__ import annotations

import math
import sys
from contextlib import contextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ETL_SRC = PROJECT_ROOT / "etl" / "src"
if str(ETL_SRC) not in sys.path:
    sys.path.insert(0, str(ETL_SRC))

class DataUnavailable(RuntimeError):
    """Raised when a required processed dataset does not exist."""


@contextmanager
def connection(*tables: str) -> Iterator[Any]:
    """Create an isolated catalog connection, or report missing optional ETL dependencies."""
    try:
        from nfl_etl.catalog import connect
    except (ImportError, ModuleNotFoundError) as exc:
        raise DataUnavailable(
            "Full analytics data is unavailable; use the bundled static demo or install etl/requirements.txt"
        ) from exc
    con = connect(only=list(tables) or None)
    try:
        available = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        missing = set(tables) - available
        if missing:
            raise DataUnavailable(f"Processed dataset unavailable: {', '.join(sorted(missing))}")
        yield con
    finally:
        con.close()


def json_safe(value: Any) -> Any:
    """Convert DuckDB values to strict JSON values (including dates and NaN)."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def rows(con: Any, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = con.execute(sql, params)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, (json_safe(value) for value in row))) for row in cursor.fetchall()]


def row(con: Any, sql: str, params: list[Any] | tuple[Any, ...] = ()) -> dict[str, Any] | None:
    result = rows(con, sql, params)
    return result[0] if result else None


def page(
    con: Any,
    base_sql: str,
    params: list[Any],
    *,
    order_by: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Execute a filtered query with an exact total and stable pagination."""
    total = con.execute(f"SELECT count(*) FROM ({base_sql}) AS filtered", params).fetchone()[0]
    items = rows(con, f"{base_sql} ORDER BY {order_by} LIMIT ? OFFSET ?", [*params, limit, offset])
    return {"items": items, "total": total, "limit": limit, "offset": offset}
