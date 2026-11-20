import shutil
from pathlib import Path

import polars as pl
import pytest
from synthetic import build_dataset

from nfl_etl.config import Paths


@pytest.fixture(scope="session")
def _raw_template(tmp_path_factory) -> Path:
    return build_dataset(tmp_path_factory.mktemp("synthetic_raw"))


@pytest.fixture()
def paths(tmp_path, _raw_template) -> Paths:
    """A fresh synthetic data dir per test (raw copied from the session template)."""
    shutil.copytree(_raw_template / "raw", tmp_path / "raw")
    return Paths(tmp_path)


@pytest.fixture()
def dims(paths):
    from nfl_etl.dims import build_dims
    return build_dims(paths, write=False)


def read_raw_tracking(paths: Paths, game_id: int) -> pl.DataFrame:
    return pl.read_csv(paths.raw_tracking / f"tracking_{game_id}.csv", null_values=["NA"], infer_schema=False)
