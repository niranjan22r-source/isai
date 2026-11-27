"""Equalizer state, presets, and persistence for ISAI.

This module owns the EQ configuration only. Actual audio processing is wired
by AudioEngine through the DSP pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QSettings, Signal

from core.app_settings import get_setting, set_setting

EQ_ENABLED_KEY = "equalizer/enabled"
EQ_MODE_KEY = "equalizer/mode"  # normal | advanced
EQ_PREAMP_KEY = "equalizer/preamp_db"
EQ_BANDS_KEY = "equalizer/bands_json"
EQ_ACTIVE_PRESET_KEY = "equalizer/active_preset"
EQ_CUSTOM_PRESETS_KEY = "equalizer/custom_presets_json"

BAND_FREQUENCIES = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
BAND_LABELS = ["31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]
MIN_GAIN_DB = -12.0
MAX_GAIN_DB = 12.0
MIN_PREAMP_DB = -12.0
MAX_PREAMP_DB = 12.0

BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "Flat": {"preamp": 0.0, "bands": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
    "Bass Boost": {"preamp": -1.5, "bands": [5, 4, 3, 2, 0, 0, 0, 0, 0, 0]},
    "Treble Boost": {"preamp": -1.5, "bands": [0, 0, 0, 0, 0, 1, 2, 3, 4, 5]},
    "Rock": {"preamp": -1.0, "bands": [4, 3, 2, 0, -1, 0, 2, 3, 4, 4]},
    "Pop": {"preamp": -1.0, "bands": [-1, 1, 3, 4, 3, 0, -1, -1, 1, 2]},
    "Classical": {"preamp": 0.0, "bands": [4, 3, 2, 1, -1, -1, 0, 2, 3, 4]},
    "Jazz": {"preamp": -0.5, "bands": [3, 2, 1, 2, -1, -1, 0, 1, 2, 3]},
    "Vocal": {"preamp": -1.0, "bands": [-2, -1, 0, 1, 3, 4, 4, 2, 0, -1]},
}


def _clamp(v: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except Exception:
        return lo
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def _normalize_bands(values: Any) -> list[float]:
    out = [0.0] * 10
    if isinstance(values, list):
        for i in range(min(10, len(values))):
            out[i] = round(_clamp(values[i], MIN_GAIN_DB, MAX_GAIN_DB), 2)
    return out


@dataclass
class EqualizerState:
    enabled: bool = True
    mode: str = "normal"  # normal | advanced
    preamp_db: float = 0.0
    bands: list[float] = field(default_factory=lambda: [0.0] * 10)
    active_preset: str = "Flat"
    custom_presets: dict[str, dict[str, Any]] = field(default_factory=dict)

    def normalized(self) -> "EqualizerState":
        self.mode = "advanced" if self.mode == "advanced" else "normal"
        self.preamp_db = round(_clamp(self.preamp_db, MIN_PREAMP_DB, MAX_PREAMP_DB), 2)
        self.bands = _normalize_bands(self.bands)
        if self.active_preset not in BUILTIN_PRESETS and self.active_preset not in self.custom_presets:
            # keep name but state is custom-ish; don't force
            pass
        clean_custom: dict[str, dict[str, Any]] = {}
        for name, preset in self.custom_presets.items():
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            if name in BUILTIN_PRESETS:
                continue
            if not isinstance(preset, dict):
                continue
            clean_custom[name] = {
                "preamp": round(_clamp(preset.get("preamp", 0.0), MIN_PREAMP_DB, MAX_PREAMP_DB), 2),
                "bands": _normalize_bands(preset.get("bands", [0.0] * 10)),
            }
        self.custom_presets = clean_custom
        return self


class EqualizerService(QObject):
    """Observable EQ state with QSettings persistence."""

    state_changed = Signal()
    preset_changed = Signal(str)

    def __init__(self, settings: QSettings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.state = self._load()

    # --------------------------------------------------------------- persistence

    def _load(self) -> EqualizerState:
        custom: dict[str, dict[str, Any]] = {}
        raw_custom = self._settings.value(EQ_CUSTOM_PRESETS_KEY, "{}", type=str)
        try:
            parsed = json.loads(raw_custom) if isinstance(raw_custom, str) else {}
            if isinstance(parsed, dict):
                custom = parsed
        except Exception:
            custom = {}
        raw_bands = self._settings.value(EQ_BANDS_KEY, "[]", type=str)
        bands = [0.0] * 10
        try:
            parsed_bands = json.loads(raw_bands) if isinstance(raw_bands, str) else []
            bands = _normalize_bands(parsed_bands)
        except Exception:
            bands = [0.0] * 10
        state = EqualizerState(
            enabled=bool(get_setting(self._settings, EQ_ENABLED_KEY, True)),
            mode=str(self._settings.value(EQ_MODE_KEY, "normal", type=str) or "normal"),
            preamp_db=round(_clamp(get_setting(self._settings, EQ_PREAMP_KEY, 0.0), MIN_PREAMP_DB, MAX_PREAMP_DB), 2),
            bands=bands,
            active_preset=str(self._settings.value(EQ_ACTIVE_PRESET_KEY, "Flat", type=str) or "Flat"),
            custom_presets=custom,
        ).normalized()
        return state

    def save(self) -> None:
        self.state.normalized()
        set_setting(self._settings, EQ_ENABLED_KEY, bool(self.state.enabled))
        self._settings.setValue(EQ_MODE_KEY, self.state.mode)
        set_setting(self._settings, EQ_PREAMP_KEY, float(self.state.preamp_db))
        self._settings.setValue(EQ_BANDS_KEY, json.dumps(self.state.bands))
        self._settings.setValue(EQ_ACTIVE_PRESET_KEY, self.state.active_preset)
        self._settings.setValue(EQ_CUSTOM_PRESETS_KEY, json.dumps(self.state.custom_presets))
        self._settings.sync()

    # ----------------------------------------------------------------- queries

    def presets(self) -> list[str]:
        return list(BUILTIN_PRESETS.keys()) + sorted(self.state.custom_presets.keys())

    def is_builtin_preset(self, name: str) -> bool:
        return name in BUILTIN_PRESETS

    # ----------------------------------------------------------------- updates

    def set_enabled(self, enabled: bool) -> None:
        self.state.enabled = bool(enabled)
        self.save()
        self.state_changed.emit()

    def set_mode(self, mode: str) -> None:
        self.state.mode = "advanced" if mode == "advanced" else "normal"
        self.save()
        self.state_changed.emit()

    def set_preamp(self, db: float) -> None:
        self.state.preamp_db = round(_clamp(db, MIN_PREAMP_DB, MAX_PREAMP_DB), 2)
        self._mark_custom_if_modified()
        self.save()
        self.state_changed.emit()

    def set_band(self, index: int, db: float) -> None:
        if not (0 <= index < 10):
            return
        self.state.bands[index] = round(_clamp(db, MIN_GAIN_DB, MAX_GAIN_DB), 2)
        self._mark_custom_if_modified()
        self.save()
        self.state_changed.emit()

    def set_all_bands(self, bands: list[float], preamp: float | None = None) -> None:
        self.state.bands = _normalize_bands(bands)
        if preamp is not None:
            self.state.preamp_db = round(_clamp(preamp, MIN_PREAMP_DB, MAX_PREAMP_DB), 2)
        self.save()
        self.state_changed.emit()

    def apply_preset(self, name: str) -> bool:
        preset = BUILTIN_PRESETS.get(name) or self.state.custom_presets.get(name)
        if not preset:
            return False
        self.state.active_preset = name
        self.state.preamp_db = round(_clamp(preset.get("preamp", 0.0), MIN_PREAMP_DB, MAX_PREAMP_DB), 2)
        self.state.bands = _normalize_bands(preset.get("bands", [0.0] * 10))
        self.save()
        self.state_changed.emit()
        self.preset_changed.emit(name)
        return True

    def reset_flat(self) -> None:
        self.apply_preset("Flat")

    def save_custom_preset(self, name: str) -> bool:
        name = (name or "").strip()
        if not name or name in BUILTIN_PRESETS:
            return False
        self.state.custom_presets[name] = {
            "preamp": float(self.state.preamp_db),
            "bands": list(self.state.bands),
        }
        self.state.active_preset = name
        self.save()
        self.state_changed.emit()
        self.preset_changed.emit(name)
        return True

    def rename_custom_preset(self, old: str, new: str) -> bool:
        new = (new or "").strip()
        if old not in self.state.custom_presets or not new or new in BUILTIN_PRESETS:
            return False
        if new in self.state.custom_presets and new != old:
            return False
        preset = self.state.custom_presets.pop(old)
        self.state.custom_presets[new] = preset
        if self.state.active_preset == old:
            self.state.active_preset = new
        self.save()
        self.state_changed.emit()
        return True

    def delete_custom_preset(self, name: str) -> bool:
        if name not in self.state.custom_presets:
            return False
        del self.state.custom_presets[name]
        if self.state.active_preset == name:
            self.state.active_preset = "Flat"
            self.apply_preset("Flat")
            return True
        self.save()
        self.state_changed.emit()
        return True

    def _mark_custom_if_modified(self) -> None:
        # If user tweaks a built-in preset, mark as Custom (unsaved) unless it still matches exactly.
        name = self.state.active_preset
        preset = BUILTIN_PRESETS.get(name) or self.state.custom_presets.get(name)
        if preset:
            same = (
                round(_clamp(preset.get("preamp", 0.0), MIN_PREAMP_DB, MAX_PREAMP_DB), 2) == self.state.preamp_db
                and _normalize_bands(preset.get("bands", [0.0] * 10)) == self.state.bands
            )
            if not same and name in BUILTIN_PRESETS:
                self.state.active_preset = "Custom"
        else:
            if name not in ("Custom", ""):
                self.state.active_preset = "Custom"
