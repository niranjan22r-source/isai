"""Cached artwork ambience for ISAI's Atmospheric surfaces.

Album artwork is sampled at a very small size (32×32) and reduced to a single
tasteful accent/glow pair.  Sampling is cheap, but it still runs on the global
Qt thread pool so a large library can never stall the UI while scrolling.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage

_CACHE_LIMIT = 256


@dataclass(frozen=True)
class AmbientPalette:
    """A restrained three-colour interpretation of one artwork image."""

    accent: str
    glow: str
    tint: str


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(round(r * 255)))),
        max(0, min(255, int(round(g * 255)))),
        max(0, min(255, int(round(b * 255)))),
    )


def _hsv_hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return _hex(r, g, b)


def extract_ambient(path: str | Path | None) -> AmbientPalette | None:
    """Return an ambient palette for an artwork file, or ``None``.

    The algorithm intentionally ignores near-black, near-white and grey pixels
    so artwork with a large neutral border still produces a useful tint.
    """
    if not path:
        return None
    try:
        image = QImage(str(path))
        if image.isNull():
            return None
        image = image.scaled(
            32,
            32,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        sum_x = 0.0
        sum_y = 0.0
        total = 0.0
        sat_sum = 0.0
        val_sum = 0.0
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.alpha() < 48:
                    continue
                h, s, v = color.hueF(), color.saturationF(), color.valueF()
                if h < 0.0:
                    h = 0.0
                if s < 0.12 or v < 0.10 or v > 0.96:
                    continue
                # Favour colourful mid-tones without letting a single bright
                # pixel dominate the result.
                weight = s * (1.0 - abs(v - 0.55))
                if weight <= 0.0:
                    continue
                angle = h * math.tau
                sum_x += math.cos(angle) * weight
                sum_y += math.sin(angle) * weight
                sat_sum += s * weight
                val_sum += v * weight
                total += weight
        if total <= 0.0:
            return None
        hue = (math.atan2(sum_y, sum_x) / math.tau) % 1.0
        sat = max(0.20, min(0.70, sat_sum / total))
        val = max(0.18, min(0.86, val_sum / total))

        accent = _hsv_hex(hue, min(0.78, sat + 0.08), min(0.92, val + 0.08))
        glow = _hsv_hex(hue, max(0.25, sat - 0.08), max(0.20, val * 0.42))
        tint = _hsv_hex(hue, max(0.18, sat - 0.24), max(0.08, val * 0.17))
        return AmbientPalette(accent=accent, glow=glow, tint=tint)
    except Exception:
        return None


class _WorkerSignals(QObject):
    finished = Signal(str, object)


class _AmbientWorker(QRunnable):
    def __init__(self, path: str, signals: _WorkerSignals) -> None:
        super().__init__()
        self._path = path
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D401 - QRunnable API
        self._signals.finished.emit(self._path, extract_ambient(self._path))


class AmbientPaletteService(QObject):
    """Shared, bounded artwork-ambience cache with background extraction."""

    palette_ready = Signal(str, object)  # artwork path, AmbientPalette

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: dict[str, tuple[int, AmbientPalette]] = {}
        self._pending: set[str] = set()
        self._signals = _WorkerSignals(self)
        self._signals.finished.connect(self._on_finished)

    def cached(self, path: str | Path | None) -> AmbientPalette | None:
        if not path:
            return None
        key = str(path)
        try:
            mtime = Path(key).stat().st_mtime_ns
        except Exception:
            return None
        entry = self._cache.get(key)
        if entry is not None and entry[0] == mtime:
            return entry[1]
        return None

    def request(self, path: str | Path | None) -> AmbientPalette | None:
        """Return a cached palette and start extraction when needed."""
        if not path:
            return None
        key = str(path)
        cached = self.cached(key)
        if cached is not None:
            return cached
        if key not in self._pending:
            try:
                if not Path(key).is_file():
                    return None
                self._pending.add(key)
                QThreadPool.globalInstance().start(_AmbientWorker(key, self._signals))
            except Exception:
                self._pending.discard(key)
        return None

    def _on_finished(self, path: str, palette: object) -> None:
        self._pending.discard(path)
        if not isinstance(palette, AmbientPalette):
            return
        try:
            mtime = Path(path).stat().st_mtime_ns
        except Exception:
            mtime = 0
        self._cache[path] = (mtime, palette)
        if len(self._cache) > _CACHE_LIMIT:
            for old_key in list(self._cache)[: _CACHE_LIMIT // 4]:
                self._cache.pop(old_key, None)
        self.palette_ready.emit(path, palette)


_DEFAULT_SERVICE: AmbientPaletteService | None = None


def ambient_service() -> AmbientPaletteService:
    """Return the process-wide ambience cache used by all surfaces."""
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = AmbientPaletteService()
    return _DEFAULT_SERVICE


def ambient_gradient_qss(
    palette: AmbientPalette | None,
    *,
    dark: bool,
    base: str,
    fallback_glow: str,
) -> str:
    """Build a subtle QSS gradient for a page/hero/panel.

    Dark surfaces use a low-glow tint near the top-left. Light surfaces use a
    soft wash of the same hue so the result still feels intentional rather than
    like an inverted dark theme.
    """
    if palette is None:
        if dark:
            return (
                "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {fallback_glow}, stop:0.62 {base}, stop:1 {base})"
            )
        return (
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {fallback_glow}, stop:0.62 {base}, stop:1 {base})"
        )
    if dark:
        return (
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {palette.glow}, stop:0.55 {base}, stop:1 {base})"
        )
    # Blend the artwork tint toward paper so the light theme stays readable.
    tint = palette.tint
    return (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        f"stop:0 {tint}, stop:0.48 {base}, stop:1 {base})"
    )
