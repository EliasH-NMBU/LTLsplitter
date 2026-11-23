"""Where evaluation data goes by default: a `data/` folder in the project checkout when the app
runs from source (or from the PyInstaller binary in its dist/ folder), else in the home folder.
The user can change it on page 1 (stored in QSettings)."""

from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT_SETTING = "evaluation/data_root"


def _project_root() -> Path | None:
    candidates = [Path(__file__).resolve().parents[3]]  # src/ltlsplitter/core/ -> checkout
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().parent.parent)  # dist/ -> checkout
    return next((c for c in candidates if (c / "pyproject.toml").is_file()), None)


def default_data_root() -> Path:
    root = _project_root()
    return root / "data" if root else Path.home() / "LTLsplitter_data"
