"""Zero-install launcher: `.venv/bin/python etl/scripts/etl.py <command>` (see etl/README.md)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nfl_etl.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
