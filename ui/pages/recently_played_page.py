"""Recently Played page: real playback history from the library database."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase, TrackRecord
from ui.components.empty_state import EmptyState
from ui.components.track_table import configure_track_table, decorate_track_row
from ui.pages.base_page import BasePage
from ui.player_bar import format_time


class RecentlyPlayedPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Recently Played", "Pick up where you left off.", parent=parent)
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self._tracks: list[TrackRecord] = []

        self.table = QTableWidget(0, 4, self)
        self.table.setObjectName("recentTable")
        self.table.setHorizontalHeaderLabels(["Title", "Artist", "Album", "Duration"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        configure_track_table(self.table)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._play_selected)
        self.table.setMinimumHeight(300)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "recent",
            "Nothing played yet",
            "Tracks you listen to from your library will appear here.",
            parent=self,
        )
        self.empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.empty_state, 1)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    def refresh_library(self) -> None:
        try:
            self._tracks = self._db.get_recently_played(limit=100)
        except Exception:
            self._tracks = []
        self.table.setRowCount(len(self._tracks))
        for row_idx, track in enumerate(self._tracks):
            values = [track.title, track.artist, track.album, format_time(track.duration)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(value)
                self.table.setItem(row_idx, col, item)
            decorate_track_row(self.table, row_idx, 0, track)
        has = bool(self._tracks)
        self.table.setVisible(has)
        self.empty_state.setVisible(not has)

    def _play_selected(self) -> None:
        row = self.table.currentRow()
        if not 0 <= row < len(self._tracks):
            return
        track = self._tracks[row]
        if Path(track.file_path).exists():
            self._engine.open_files([track.file_path], autoplay=True)

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.empty_state.refresh_theme(colors)
