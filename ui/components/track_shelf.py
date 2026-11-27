"""Horizontal, lazily populated artwork shelf."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QWidget

from core.theme_manager import ThemeColors
from services.library_database import TrackRecord
from ui.components.track_tile import TrackTile


class TrackShelf(QScrollArea):
    """A single-row shelf of artwork tiles with an intentional gutter."""

    def __init__(
        self,
        on_play: Callable[[list[TrackRecord], int], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("trackShelf")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(226)
        self._on_play = on_play
        self._tracks: list[TrackRecord] = []
        self._colors: ThemeColors | None = None

        self._canvas = QWidget(self)
        self._canvas.setObjectName("shelfCanvas")
        self._row = QHBoxLayout(self._canvas)
        self._row.setContentsMargins(0, 0, 0, 4)
        self._row.setSpacing(12)
        self._row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._row.addStretch(1)
        self.setWidget(self._canvas)

    def set_tracks(self, tracks: Iterable[TrackRecord]) -> None:
        self._tracks = list(tracks)
        self._clear_tiles()
        if not self._tracks:
            return
        for index, track in enumerate(self._tracks):
            tile = TrackTile(
                title=track.title or "Unknown title",
                artist=track.artist or "Unknown artist",
                artwork_path=track.artwork_path,
                duration=track.duration,
                payload=track,
                parent=self._canvas,
            )
            tile.clicked.connect(lambda _tile, i=index: self._play_index(i))
            tile.double_clicked.connect(lambda _tile, i=index: self._play_index(i))
            if self._colors is not None:
                tile.refresh_theme(self._colors)
            self._row.insertWidget(self._row.count() - 1, tile)

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        for tile in self._canvas.findChildren(TrackTile):
            tile.refresh_theme(colors)

    def _clear_tiles(self) -> None:
        for tile in self._canvas.findChildren(TrackTile):
            self._row.removeWidget(tile)
            tile.setParent(None)
            tile.deleteLater()

    def _play_index(self, index: int) -> None:
        if self._on_play is not None and 0 <= index < len(self._tracks):
            self._on_play(self._tracks, index)
