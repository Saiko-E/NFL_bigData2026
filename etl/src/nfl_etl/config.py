"""Paths, constants and validation thresholds for the ETL."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PIPELINE_VERSION = "1.0.0"
# etl/src/nfl_etl/config.py -> project root is three levels above the package dir
PROJECT_ROOT = Path(__file__).resolve().parents[3]

FIELD_LENGTH = 120.0  # yards, end zones included (raw x range)
FIELD_WIDTH = 53.3  # yards (raw y range)
FPS = 10  # tracking frequency (frames per second)
EXPECTED_SEASON = 2021
EXPECTED_WEEKS = tuple(range(1, 9))
PLAYERS_PER_FRAME = 22
ENTITIES_PER_FRAME = 23  # 22 players + football

# Tolerances for value validation. Rows are flagged (qc_flags), never dropped, on these rules.
# Measured on the Sep-2021 games (weeks 1-4): players max s=11.2, |a|=14.2, dis=2.12;
# ball max s=28.3, |a|=50.7, dis=8.46 (ball dis spikes are inconsistent with ball speed).
# Positions: players/ball legitimately step up to ~4 yd outside the field lines.
X_RANGE = (-5.0, 125.0)
Y_RANGE = (-5.0, 58.3)
LIMITS = {
    "player": {"s": 15.0, "a": 25.0, "dis": 2.5},
    "ball": {"s": 45.0, "a": 80.0, "dis": 3.5},  # 3.5 yd/frame = 35 yd/s, above any real throw
}
LOS_TOLERANCE_YDS = 3.0  # ball-at-snap vs absoluteYardlineNumber
MAX_EXCLUSION_KEYS = 500  # key examples stored per exclusion record

SNAP_EVENTS = ("ball_snap", "autoevent_ballsnap")
PFF_ROLES = ("Pass", "Pass Block", "Coverage", "Pass Route", "Pass Rush")
PASS_RESULTS = ("C", "I", "S", "R", "IN")


@dataclass(frozen=True)
class Paths:
    data_dir: Path

    @classmethod
    def default(cls) -> "Paths":
        return cls(Path(os.environ.get("NFL_DATA_DIR", PROJECT_ROOT / "data")))

    @property
    def raw(self) -> Path:
        return self.data_dir / "raw"

    @property
    def raw_tracking(self) -> Path:
        return self.raw / "tracking"

    @property
    def processed(self) -> Path:
        return self.data_dir / "processed"

    @property
    def dim(self) -> Path:
        return self.processed / "dim"

    @property
    def tracking(self) -> Path:
        return self.processed / "tracking"

    @property
    def agg(self) -> Path:
        return self.processed / "agg"

    @property
    def manifest(self) -> Path:
        return self.processed / "_manifest"

    @property
    def reports(self) -> Path:
        return self.data_dir / "reports"
