"""Centralized ISAI settings keys, defaults, and typed access.

Settings are persisted in QSettings (INI, user scope) through the existing
ThemeManager settings store, so there is one settings file and one source of
truth. Invalid values fall back to safe defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QSettings

# Appearance (owned historically by ThemeManager, still stored here)
THEME_KEY = "appearance/theme"
REDUCED_MOTION_KEY = "appearance/reduced_motion"
AMBIENT_ARTWORK_KEY = "appearance/ambient_artwork_colors"

# Playback
VOLUME_KEY = "playback/default_volume"
RESUME_POSITION_KEY = "playback/resume_position"
REMEMBER_STATE_KEY = "playback/remember_state"
DEFAULT_REPEAT_KEY = "playback/default_repeat"
DEFAULT_SHUFFLE_KEY = "playback/default_shuffle"
PLAYBACK_NOTIFICATIONS_KEY = "desktop/notifications_enabled"  # legacy key preserved

# Library
SCAN_ON_STARTUP_KEY = "library/scan_on_startup"
LIBRARY_FOLDERS_KEY = "library/folders"  # legacy/fallback; DB table is primary

# Desktop integration
CLOSE_TO_TRAY_KEY = "desktop/close_to_tray"

# Cache
ARTWORK_CACHE_LIMIT_MB_KEY = "cache/artwork_cache_limit_mb"

DEFAULTS: dict[str, Any] = {
    THEME_KEY: "dark",
    REDUCED_MOTION_KEY: False,
    AMBIENT_ARTWORK_KEY: True,
    VOLUME_KEY: 70,
    RESUME_POSITION_KEY: True,
    REMEMBER_STATE_KEY: True,
    DEFAULT_REPEAT_KEY: "off",
    DEFAULT_SHUFFLE_KEY: False,
    PLAYBACK_NOTIFICATIONS_KEY: True,
    SCAN_ON_STARTUP_KEY: False,
    LIBRARY_FOLDERS_KEY: [],
    CLOSE_TO_TRAY_KEY: True,
    ARTWORK_CACHE_LIMIT_MB_KEY: 512,
}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default


def _as_int(value: Any, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        v = int(value)
    except Exception:
        return default
    if minimum is not None:
        v = max(minimum, v)
    if maximum is not None:
        v = min(maximum, v)
    return v


def _as_str(value: Any, default: str, allowed: set[str] | None = None) -> str:
    v = str(value).strip() if value is not None else ""
    if not v:
        return default
    if allowed is not None and v not in allowed:
        return default
    return v


def get_setting(settings: QSettings, key: str, default: Any = None) -> Any:
    if default is None:
        default = DEFAULTS.get(key)
    raw = settings.value(key, default)
    if key in {REDUCED_MOTION_KEY, AMBIENT_ARTWORK_KEY, RESUME_POSITION_KEY, REMEMBER_STATE_KEY, DEFAULT_SHUFFLE_KEY, PLAYBACK_NOTIFICATIONS_KEY, SCAN_ON_STARTUP_KEY, CLOSE_TO_TRAY_KEY}:
        return _as_bool(raw, bool(default))
    if key == VOLUME_KEY:
        return _as_int(raw, int(default), 0, 100)
    if key == ARTWORK_CACHE_LIMIT_MB_KEY:
        return _as_int(raw, int(default), 64, 4096)
    if key == DEFAULT_REPEAT_KEY:
        return _as_str(raw, str(default), {"off", "all", "one"})
    if key == THEME_KEY:
        return _as_str(raw, str(default), {"dark", "light", "system"})
    if key == LIBRARY_FOLDERS_KEY:
        if isinstance(raw, list):
            return [str(x) for x in raw if str(x).strip()]
        if isinstance(raw, str) and raw.strip():
            # QSettings may store as string in INI.
            return [p for p in raw.split(";") if p.strip()]
        return list(default) if isinstance(default, list) else []
    return raw if raw is not None else default


def set_setting(settings: QSettings, key: str, value: Any) -> None:
    settings.setValue(key, value)
