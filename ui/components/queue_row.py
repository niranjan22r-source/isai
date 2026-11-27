"""Readable queue row used by the Atmospheric queue panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.theme_manager import ThemeColors
from services.queue_manager import QueueItem
from ui.components.artwork import artwork_ready_connect, request_rounded_pixmap
from ui.player_bar import format_time


class QueueRow(QWidget):
    ROW_HEIGHT = 56

    def __init__(
        self,
        item: QueueItem,
        index: int,
        is_current: bool,
        colors: ThemeColors,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("queueRow")
        self.setFixedHeight(self.ROW_HEIGHT)
        self._colors = colors
        self._item = item
        self._art_key = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 10, 6)
        layout.setSpacing(10)

        self.number_label = QLabel("▶" if is_current else f"{index + 1}", self)
        self.number_label.setObjectName("queueRowNumber")
        self.number_label.setFixedWidth(18)
        self.number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.number_label)

        self.art_label = QLabel(self)
        self.art_label.setObjectName("queueRowArt")
        self.art_label.setFixedSize(40, 40)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.art_label)

        text = QWidget(self)
        from PySide6.QtWidgets import QVBoxLayout

        text_layout = QVBoxLayout(text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        self.title_label = QLabel(item.title or item.path.stem, text)
        self.title_label.setObjectName("queueRowTitle")
        self.artist_label = QLabel(item.artist or "Unknown artist", text)
        self.artist_label.setObjectName("queueRowArtist")
        for label in (self.title_label, self.artist_label):
            label.setWordWrap(False)
            fm = label.fontMetrics()
            label.setText(fm.elidedText(label.text(), Qt.TextElideMode.ElideRight, 210))
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.artist_label)
        layout.addWidget(text, 1)

        self.duration_label = QLabel(
            format_time(item.duration) if item.duration else "", self
        )
        self.duration_label.setObjectName("queueRowDuration")
        self.duration_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.duration_label)

        artwork_ready_connect(self._on_art_ready)
        self._load_art()

    def _load_art(self) -> None:
        pixmap, key = request_rounded_pixmap(
            self._item.artwork_path,
            40,
            9,
            fallback_color=self._colors.surface_alt,
            fallback_icon="note",
        )
        self._art_key = key
        if pixmap is not None:
            self.art_label.setPixmap(pixmap)

    def _on_art_ready(self, key, pixmap) -> None:
        if key != self._art_key or pixmap is None:
            return
        try:
            self.art_label.setPixmap(pixmap)
        except Exception:
            pass

    def set_current(self, is_current: bool, index: int) -> None:
        """Cheap in-place current-row update, avoiding a full queue rebuild."""
        text = "▶" if is_current else f"{index + 1}"
        if self.number_label.text() != text:
            self.number_label.setText(text)
