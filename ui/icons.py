"""Self-contained symbolic icon set for ISAI.

Icons are tiny inline SVGs rendered with QtSvg, recolored at runtime, and
cached. This keeps the application dependency-free while still providing
crisp, theme-aware symbolic icons.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS: dict[str, str] = {
    "home": (
        '<path d="M3.5 10.5 12 3.5l8.5 7"/>'
        '<path d="M5.5 9.5V20h13V9.5"/>'
        '<path d="M9.5 20v-5h5v5"/>'
    ),
    "songs": (
        '<path d="M9 18V5l10-2v13"/>'
        '<circle cx="6" cy="18" r="3"/>'
        '<circle cx="16" cy="16" r="3"/>'
    ),
    "albums": (
        '<circle cx="12" cy="12" r="8.5"/>'
        '<circle cx="12" cy="12" r="2.25"/>'
    ),
    "artists": (
        '<circle cx="12" cy="8" r="3.75"/>'
        '<path d="M4.5 20.5c0-3.6 3.6-5.5 7.5-5.5s7.5 1.9 7.5 5.5"/>'
    ),
    "playlists": (
        '<path d="M4 6h11"/><path d="M4 11h11"/><path d="M4 16h7"/>'
        '<path d="M18 5v10"/><circle cx="15.5" cy="16.5" r="2.5"/>'
    ),
    "favorites": (
        '<path d="M12 20.5s-7.3-4.7-9.2-8.7A5.1 5.1 0 0 1 12 6.3'
        'a5.1 5.1 0 0 1 9.2 5.5c-1.9 4-9.2 8.7-9.2 8.7z"/>'
    ),
    "recent": (
        '<circle cx="12" cy="12" r="8.5"/>'
        '<path d="M12 7.5V12l3 2"/>'
    ),
    "settings": (
        '<path d="M4 7h7"/><path d="M15 7h5"/><circle cx="13" cy="7" r="2.2"/>'
        '<path d="M4 12h3"/><path d="M11 12h9"/><circle cx="9" cy="12" r="2.2"/>'
        '<path d="M4 17h9"/><path d="M17 17h3"/><circle cx="15" cy="17" r="2.2"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="6.5"/>'
        '<path d="m16 16 4.5 4.5"/>'
    ),
    "sort": (
        '<path d="M7 4v16"/><path d="m3.5 7.5 3.5-3.5 3.5 3.5"/>'
        '<path d="M17 20V4"/><path d="m13.5 16.5 3.5 3.5 3.5-3.5"/>'
    ),
    "chevron-left": '<path d="m14.5 6-6 6 6 6"/>',
    "chevron-right": '<path d="m9.5 6 6 6-6 6"/>',
    "chevron-down": '<path d="m6 9.5 6 6 6-6"/>',
    "play": (
        '<path d="M8 5.4 18.4 12 8 18.6z" fill="{color}" stroke="{color}" '
        'stroke-width="1" stroke-linejoin="round"/>'
    ),
    "pause": (
        '<rect x="7.2" y="5" width="3.4" height="14" rx="1.2" '
        'fill="{color}" stroke="none"/>'
        '<rect x="13.4" y="5" width="3.4" height="14" rx="1.2" '
        'fill="{color}" stroke="none"/>'
    ),
    "previous": (
        '<path d="M19 5.5 8.5 12 19 18.5z" fill="{color}" stroke="none"/>'
        '<path d="M5.5 5v14"/>'
    ),
    "next": (
        '<path d="M5 5.5 15.5 12 5 18.5z" fill="{color}" stroke="none"/>'
        '<path d="M18.5 5v14"/>'
    ),
    "volume": (
        '<path d="M4 9.5h3.5L13 5.5v13L7.5 14.5H4z" '
        'fill="{color}" stroke="none"/>'
        '<path d="M16 9a4.5 4.5 0 0 1 0 6"/>'
        '<path d="M18.5 6.5a8 8 0 0 1 0 11"/>'
    ),
    "volume-low": (
        '<path d="M4 9.5h3.5L13 5.5v13L7.5 14.5H4z" '
        'fill="{color}" stroke="none"/>'
        '<path d="M16 9a4.5 4.5 0 0 1 0 6"/>'
    ),
    "volume-muted": (
        '<path d="M4 9.5h3.5L13 5.5v13L7.5 14.5H4z" '
        'fill="{color}" stroke="none"/>'
        '<path d="m16.5 9.5 4.5 5"/>'
        '<path d="m21 9.5-4.5 5"/>'
    ),
    "queue": (
        '<path d="M4 6h14"/><path d="M4 12h14"/><path d="M4 18h9"/>'
        '<path d="m16.5 15.5 4 2.5-4 2.5z" fill="{color}" stroke="none"/>'
    ),
    "shuffle": (
        '<path d="M16 3h5v5"/><path d="M4 20 21 3"/>'
        '<path d="M21 16v5h-5"/><path d="M15 15l6 6"/>'
        '<path d="M4 4l5 5"/>'
    ),
    "repeat": (
        '<path d="M17 2l4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/>'
        '<path d="M7 22l-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>'
    ),
    "repeat-one": (
        '<path d="M17 2l4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/>'
        '<path d="M7 22l-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>'
        '<path d="M11 10h1v4"/><path d="M10 14h4"/>'
    ),
    "expand": (
        '<path d="M9 4H4v5"/><path d="M15 4h5v5"/>'
        '<path d="M9 20H4v-5"/><path d="M15 20h5v-5"/>'
    ),
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "sun": (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2.5v2"/><path d="M12 19.5v2"/>'
        '<path d="M2.5 12h2"/><path d="M19.5 12h2"/>'
        '<path d="m5.2 5.2 1.4 1.4"/><path d="m17.4 17.4 1.4 1.4"/>'
        '<path d="m18.8 5.2-1.4 1.4"/><path d="m6.6 17.4-1.4 1.4"/>'
    ),
    "moon": (
        '<path d="M20.5 13.2A8 8 0 1 1 10.8 3.5a6.3 6.3 0 0 0 9.7 9.7z"/>'
    ),
    "note": (
        '<path d="M9 18V5l10-2v13"/>'
        '<circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>'
    ),
    "lyrics": (
        '<path d="M5 6h14"/><path d="M5 10h14"/><path d="M5 14h10"/><path d="M5 18h7"/>'
    ),
    "miniplayer": (
        '<rect x="4" y="5" width="16" height="14" rx="2"/>'
        '<path d="M8 16h8"/>'
    ),
    "equalizer": (
        '<path d="M6 4v16"/><circle cx="6" cy="9" r="1.8" fill="{color}" stroke="none"/>'
        '<path d="M12 4v16"/><circle cx="12" cy="14" r="1.8" fill="{color}" stroke="none"/>'
        '<path d="M18 4v16"/><circle cx="18" cy="8" r="1.8" fill="{color}" stroke="none"/>'
    ),
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def _device_pixel_ratio() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen is not None else 1.0


@lru_cache(maxsize=256)
def _render(name: str, color: str, size: int, ratio: float) -> QPixmap:
    body = _ICONS[name].replace("{color}", color)
    renderer = QSvgRenderer(QByteArray(_SVG.format(color=color, body=body).encode()))
    pixel_size = max(1, int(round(size * ratio)))
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon(name: str, color: str, size: int = 20) -> QIcon:
    """Return a theme-colored symbolic icon.

    Args:
        name: Key from the built-in icon set.
        color: Hex color used for the icon strokes and fills.
        size: Logical icon size in pixels.
    """
    if name not in _ICONS:
        raise KeyError(f"Unknown icon: {name!r}")
    return QIcon(_render(name, color, size, _device_pixel_ratio()))


def available_icons() -> tuple[str, ...]:
    return tuple(sorted(_ICONS))
