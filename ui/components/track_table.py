"""Shared sizing/artwork decoration for the library track tables."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from services.library_database import TrackRecord
from ui.components.artwork import artwork_ready_connect, request_rounded_pixmap

ROW_HEIGHT = 54
HEADER_HEIGHT = 40
ARTWORK_SIZE = 38


def configure_track_table(
    table: QTableWidget,
    *,
    row_height: int = ROW_HEIGHT,
    artwork_size: int = ARTWORK_SIZE,
) -> None:
    """Apply the Atmospheric list rhythm without changing table semantics."""
    table.verticalHeader().setDefaultSectionSize(int(row_height))
    table.verticalHeader().setMinimumSectionSize(int(row_height))
    table.horizontalHeader().setFixedHeight(HEADER_HEIGHT)
    table.setIconSize(QSize(int(artwork_size), int(artwork_size)))
    table.setWordWrap(False)
    table.setShowGrid(False)


_ART_ICON_ROLE = 0x0151  # UserRole+81, stores artwork key tuple


def _ensure_artwork_handler(table: QTableWidget) -> None:
    if getattr(table, "_artwork_handler", False):
        return
    def _on_ready(key, pixmap):
        if pixmap is None:
            return
        try:
            rows = table.rowCount()
            cols = table.columnCount()
        except Exception:
            return
        for r in range(rows):
            for c in range(cols):
                it = table.item(r, c)
                if it is None:
                    continue
                if it.data(_ART_ICON_ROLE) == key:
                    try:
                        it.setIcon(QIcon(pixmap))
                    except Exception:
                        pass
    try:
        artwork_ready_connect(_on_ready)
        table._artwork_handler = True
        table._artwork_ready_slot = _on_ready  # keep ref
    except Exception:
        pass


def decorate_track_row(
    table: QTableWidget,
    row: int,
    title_column: int,
    track: TrackRecord,
    *,
    artwork_size: int = ARTWORK_SIZE,
) -> None:
    """Attach a cached/async rounded thumbnail to the row's title item."""
    item = table.item(row, title_column)
    if not isinstance(item, QTableWidgetItem):
        return
    _ensure_artwork_handler(table)
    pixmap, key = request_rounded_pixmap(
        track.artwork_path,
        artwork_size,
        8,
        fallback_color="#6a738233",
        fallback_icon="note",
    )
    if key is not None:
        item.setData(_ART_ICON_ROLE, key)
    if pixmap is not None:
        item.setIcon(QIcon(pixmap))
    item.setToolTip(track.file_path)
