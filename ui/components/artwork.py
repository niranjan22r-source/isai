"""Cached, lightweight artwork helpers for Atmospheric lists and cards.

Artwork decode/scale can block the UI when tracks change or large lists refresh.
This module keeps a bounded pixmap cache and offers async loading so widgets can
show a placeholder immediately and update when the pixmap is ready.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QRectF, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

from services.artwork_cache import ArtworkCache
from ui.icons import icon

_CACHE: dict[tuple[str, int, int, int], QPixmap] = {}
_CACHE_LIMIT = 512
_PENDING: set[tuple[str, int, int, int]] = set()
_ARTWORK_CACHE = ArtworkCache()


class _ArtworkSignals(QObject):
    ready = Signal(object, object)  # key tuple, QPixmap|None


_SIGNALS = _ArtworkSignals()


class _ArtworkWorker(QRunnable):
    def __init__(self, key: tuple[str, int, int, int]) -> None:
        super().__init__()
        self._key = key
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D401 - QRunnable API
        path, _mtime, size, radius = self._key
        pm = _load_rounded(path, int(size), int(radius))
        _SIGNALS.ready.emit(self._key, pm)


def artwork_ready_connect(slot) -> None:
    """Connect a slot(key, pixmap) to async artwork completion."""
    try:
        _SIGNALS.ready.connect(slot)
    except Exception:
        pass


def _placeholder(size: int, radius: int, color: str, icon_name: str = "note") -> QPixmap:
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.fillPath(path, QColor(color))
    glyph_size = max(14, size // 3)
    glyph = icon(icon_name, color, glyph_size).pixmap(QSize(glyph_size, glyph_size))
    # draw a subtle glyph by painting note in a lighter/darker tone? icon() already colored.
    painter.drawPixmap(
        (size - glyph.width()) // 2,
        (size - glyph.height()) // 2,
        glyph,
    )
    painter.end()
    return canvas


def _load_rounded(path: str, size: int, radius: int) -> QPixmap | None:
    try:
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        # Decode close to target size for speed.
        orig = reader.size()
        if orig.isValid() and orig.width() > 0 and orig.height() > 0:
            scale = max(size / orig.width(), size / orig.height())
            if scale < 1.0:
                reader.setScaledSize(
                    QSize(
                        max(1, int(orig.width() * scale)),
                        max(1, int(orig.height() * scale)),
                    )
                )
        image = reader.read()
        if image.isNull():
            return None
        img = image.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
        painter.setClipPath(clip)
        x = (size - img.width()) // 2
        y = (size - img.height()) // 2
        painter.drawImage(x, y, img)
        painter.end()
        return canvas
    except Exception:
        return None


def _resolve_key(artwork_path: str | None, size: int, radius: int):
    resolved = _ARTWORK_CACHE.resolve(artwork_path)
    if resolved is None:
        return None
    try:
        mtime = int(Path(resolved).stat().st_mtime_ns)
    except Exception:
        return None
    return (resolved, mtime, int(size), int(radius))


def rounded_pixmap(
    artwork_path: str | None,
    size: int,
    radius: int = 10,
    *,
    fallback_color: str | None = None,
    fallback_icon: str = "note",
) -> QPixmap | None:
    """Return a rounded artwork pixmap, or a themed placeholder.

    This is synchronous and uses cache. For large lists/track changes, prefer
    `request_rounded_pixmap` to avoid UI-thread decode stalls.
    """
    key = _resolve_key(artwork_path, size, radius)
    if key is None:
        if fallback_color is None:
            return None
        return _placeholder(int(size), int(radius), fallback_color, fallback_icon)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    pm = _load_rounded(key[0], int(size), int(radius))
    if pm is None:
        if fallback_color is None:
            return None
        return _placeholder(int(size), int(radius), fallback_color, fallback_icon)
    _CACHE[key] = pm
    if len(_CACHE) > _CACHE_LIMIT:
        for old in list(_CACHE.keys())[: _CACHE_LIMIT // 4]:
            _CACHE.pop(old, None)
    return pm


def request_rounded_pixmap(
    artwork_path: str | None,
    size: int,
    radius: int = 10,
    *,
    fallback_color: str | None = None,
    fallback_icon: str = "note",
) -> tuple[QPixmap | None, tuple | None]:
    """Return (pixmap_or_placeholder, key_or_None).

    If not cached, schedules background load and emits `_SIGNALS.ready`.
    """
    key = _resolve_key(artwork_path, size, radius)
    if key is None:
        if fallback_color is None:
            return None, None
        return _placeholder(int(size), int(radius), fallback_color, fallback_icon), None
    cached = _CACHE.get(key)
    if cached is not None:
        return cached, key
    if key not in _PENDING:
        _PENDING.add(key)
        QThreadPool.globalInstance().start(_ArtworkWorker(key))
    if fallback_color is None:
        return None, key
    return _placeholder(int(size), int(radius), fallback_color, fallback_icon), key


def _on_ready(key, pixmap) -> None:
    try:
        _PENDING.discard(key)
    except Exception:
        pass
    if isinstance(pixmap, QPixmap) and not pixmap.isNull():
        _CACHE[key] = pixmap
        if len(_CACHE) > _CACHE_LIMIT:
            for old in list(_CACHE.keys())[: _CACHE_LIMIT // 4]:
                _CACHE.pop(old, None)


_SIGNALS.ready.connect(_on_ready)


def artwork_icon(
    artwork_path: str | None,
    size: int = 38,
    radius: int = 8,
) -> QIcon | None:
    pixmap = rounded_pixmap(artwork_path, size, radius)
    return QIcon(pixmap) if pixmap is not None else None


_BLUR_CACHE: dict[tuple[str, int, int, int], QPixmap] = {}
_BLUR_CACHE_LIMIT = 48


def blurred_artwork_pixmap(
    artwork_path: str | None,
    target_size: QSize,
    blur_radius: float = 28.0,
) -> QPixmap | None:
    """Return a lightweight blurred artwork pixmap for backgrounds."""
    key = _resolve_key(artwork_path, 128, 0)
    if key is None:
        return None
    cache_key = (key[0], key[1], max(1, target_size.width()), max(1, target_size.height()))
    cached = _BLUR_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        reader = QImageReader(key[0])
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return None
        # Downscale for cheap blur, then upscale to target.
        small = img.scaled(
            96,
            96,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        src = QPixmap.fromImage(small)
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(src)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(max(0.0, float(blur_radius)))
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        result = QPixmap(src.size())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        scene.render(painter, QRectF(result.rect()), QRectF(src.rect()))
        painter.end()
        final = result.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Center-crop to exact target.
        if final.size() != target_size:
            x = max(0, (final.width() - target_size.width()) // 2)
            y = max(0, (final.height() - target_size.height()) // 2)
            final = final.copy(x, y, target_size.width(), target_size.height())
        _BLUR_CACHE[cache_key] = final
        if len(_BLUR_CACHE) > _BLUR_CACHE_LIMIT:
            for old in list(_BLUR_CACHE.keys())[: _BLUR_CACHE_LIMIT // 4]:
                _BLUR_CACHE.pop(old, None)
        return final
    except Exception:
        return None
