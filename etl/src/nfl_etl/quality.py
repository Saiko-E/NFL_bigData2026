"""Collects data-quality checks and exclusions. Nothing is dropped without a record here."""
from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from .config import MAX_EXCLUSION_KEYS


class SchemaError(Exception):
    """A source file does not match the expected structure."""


@dataclass
class QualityLog:
    scope: str
    checks: list[dict] = field(default_factory=list)
    exclusions: list[dict] = field(default_factory=list)

    def check(self, name: str, count: int, *, severity: str = "warn", detail: str = "",
              total: int | None = None) -> None:
        """Record a check. count == 0 means it passed (severity becomes 'ok')."""
        count = int(count)
        self.checks.append({
            "scope": self.scope, "name": name, "count": count,
            "total": None if total is None else int(total),
            "severity": severity if count else "ok", "detail": detail,
        })

    def exclude(self, source: str, rule: str, reason: str, rows: pl.DataFrame,
                key_cols: list[str], *, action: str = "dropped") -> None:
        """Log rows removed from the output (action='dropped'). Also records a check."""
        n = rows.height
        self.check(rule, n, detail=f"{action}: {reason}")
        if n:
            self.exclusions.append({
                "scope": self.scope, "source": source, "rule": rule, "reason": reason,
                "action": action, "n_rows": n,
                "keys": rows.select(key_cols).head(MAX_EXCLUSION_KEYS).to_dicts(),
            })
