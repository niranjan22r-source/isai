"""Resource path helpers for source and PyInstaller-frozen runs."""

from __future__ import annotations

import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return app_base_dir().joinpath(*parts)
