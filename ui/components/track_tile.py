"""Artwork-led track tiles used by the Atmospheric home shelves."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from core.theme_manager import ThemeColors
from ui.components.artwork import rounded_pixmap
from ui.player_bar import format_time

ART_SIZE = 140
TILE_WIDTH = 156


class TrackTile(QFrame):
    """A compact editorial tile: artwork, title, artist and duration."""

    clicked = Signal(object)  # payload track
    double_clicked = Signal(object)

    def __init__(
        self,
        title: str,
        artist: str,
        artwork_path: str | None = None,
        duration: int = 0,
        payload: object = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("trackTile")
        self.setFixedWidth(TILE_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(f"{title} — {artist}" if artist else title)
        self.payload = payload
        self._artwork_path = artwork_path
        self._title = title
        self._artist = artist
        self._duration = duration
        self._colors: ThemeColors | None = None
        self._art_loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 10)
        layout.setSpacing(8)

        self.art_label = QLabel(self)
        self.art_label.setObjectName("trackTileArt")
        self.art_label.setFixedSize(ART_SIZE, ART_SIZE)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.art_label)

        self.title_label = QLabel(self)
        self.title_label.setObjectName("trackTileTitle")
        self.title_label.setWordWrap(False)
        layout.addWidget(self.title_label)

        self.artist_label = QLabel(self)
        self.artist_label.setObjectName("trackTileArtist")
        self.artist_label.setWordWrap(False)
        layout.addWidget(self.artist_label)
        self._update_text()

    def _update_text(self) -> None:
        width = max(60, self.width() - 16)
        fm = self.title_label.fontMetrics()
        self.title_label.setText(
            fm.elidedText(self._title, Qt.TextElideMode.ElideRight, width)
        )
        subtitle = self._artist or "Unknown artist"
        if self._duration > 0:
            subtitle = f"{subtitle} · {format_time(self._duration)}"
        sfm = self.artist_label.fontMetrics()
        self.artist_label.setText(
            sfm.elidedText(subtitle, Qt.TextElideMode.ElideRight, width)
        )
        self.artist_label.setToolTip(subtitle)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_text()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self)
        super().mouseDoubleClickEvent(event)

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self._art_loaded = False
        self._update_art()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._art_loaded:
            self._update_art()
        super().paintEvent(event)

    def _update_art(self) -> None:
        if self._colors is None:
            return
        pixmap = rounded_pixmap(
            self._artwork_path,
            ART_SIZE,
            13,
            fallback_color=self._colors.surface_alt,
            fallback_icon="note",
        )
        if pixmap is not None:
            self.art_label.setPixmap(pixmap)
        self._art_loaded = True
