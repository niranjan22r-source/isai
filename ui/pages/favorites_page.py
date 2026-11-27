"""Favorites page: persisted favorite tracks."""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase, TrackRecord
from ui.components.empty_state import EmptyState
from ui.components.playlist_dialog import PlaylistDialog
from ui.components.search_field import SearchField
from ui.components.sort_combo import SortComboBox
from ui.components.track_info_dialog import TrackInfoDialog
from ui.components.track_table import configure_track_table, decorate_track_row
from ui.pages.base_page import BasePage
from ui.player_bar import format_time

SORT_MAP = {
    "Title": "title",
    "Artist": "artist",
    "Album": "album",
    "Duration": "duration",
}


class FavoritesPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Favorites", "The songs you love most.", parent=parent)
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self._tracks: list[TrackRecord] = []
        self._sort_descending = False

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.refresh_library)

        toolbar = QFrame(self)
        toolbar.setObjectName("toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(10)
        self.search_field = SearchField("Search favorites", toolbar)
        self.search_field.setFixedHeight(38)
        self.search_field.textChanged.connect(lambda _t: self._search_timer.start())
        tb.addWidget(self.search_field, 1)

        self.sort_combo = SortComboBox(toolbar)
        self.sort_combo.addItems(list(SORT_MAP.keys()))
        self.sort_combo.setFixedHeight(38)
        self.sort_combo.currentTextChanged.connect(self.refresh_library)
        tb.addWidget(self.sort_combo)
        self.sort_dir_button = QPushButton("Asc", toolbar)
        self.sort_dir_button.setObjectName("sortDirButton")
        self.sort_dir_button.setFixedHeight(38)
        self.sort_dir_button.clicked.connect(self._toggle_sort_direction)
        tb.addWidget(self.sort_dir_button)

        self.play_all_button = QPushButton("Play all", toolbar)
        self.play_all_button.setObjectName("primaryButton")
        self.play_all_button.clicked.connect(self._play_all)
        tb.addWidget(self.play_all_button)
        self.shuffle_button = QPushButton("Shuffle", toolbar)
        self.shuffle_button.setObjectName("secondaryButton")
        self.shuffle_button.clicked.connect(self._shuffle_all)
        tb.addWidget(self.shuffle_button)

        self.count_label = QLabel("0 songs", toolbar)
        self.count_label.setObjectName("countLabel")
        tb.addWidget(self.count_label)
        self.body.addWidget(toolbar)

        self.table = QTableWidget(0, 5, self)
        self.table.setObjectName("songsTable")
        self.table.setHorizontalHeaderLabels(
            ["Title", "Artist", "Album", "Duration", "Format"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        configure_track_table(self.table)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._play_selected)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.body.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "favorites",
            "No favorite songs yet",
            "Songs you mark with a heart will appear here.",
            parent=self,
        )
        self.empty_state.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.body.addWidget(self.empty_state, 1)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    def _toggle_sort_direction(self) -> None:
        self._sort_descending = not self._sort_descending
        self.sort_dir_button.setText("Desc" if self._sort_descending else "Asc")
        self.refresh_library()

    def refresh_library(self) -> None:
        query = self.search_field.text().strip().lower()
        try:
            tracks = self._db.get_favorites()
        except Exception:
            tracks = []
        if query:
            tracks = [
                t
                for t in tracks
                if query in (t.title or "").lower()
                or query in (t.artist or "").lower()
                or query in (t.album or "").lower()
            ]
        sort_key = SORT_MAP.get(self.sort_combo.currentText(), "title")
        reverse = self._sort_descending
        if sort_key == "duration":
            tracks.sort(key=lambda t: int(t.duration or 0), reverse=reverse)
        else:
            tracks.sort(key=lambda t: str(getattr(t, sort_key, "") or "").lower(), reverse=reverse)
        self._tracks = tracks
        self.table.setRowCount(len(self._tracks))
        for row, track in enumerate(self._tracks):
            values = [
                track.title,
                track.artist,
                track.album,
                format_time(track.duration),
                track.format.upper(),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.UserRole, track.file_path)
                self.table.setItem(row, col, item)
            decorate_track_row(self.table, row, 0, track)
        count = len(self._tracks)
        noun = "song" if count == 1 else "songs"
        self.count_label.setText(f"{count} matching {noun}" if query else f"{count} {noun}")
        has = bool(self._tracks)
        self.table.setVisible(has)
        self.empty_state.setVisible(not has)
        if not has and query:
            self.empty_state.set_message("No matching favorites", "Try a different search term.")
        elif not has:
            self.empty_state.set_message(
                "No favorite songs yet",
                "Songs you mark with a heart will appear here.",
            )

    def _selected_tracks(self) -> list[TrackRecord]:
        tracks = []
        for idx in self.table.selectionModel().selectedRows():
            row = idx.row()
            if 0 <= row < len(self._tracks):
                tracks.append(self._tracks[row])
        return tracks

    def _refresh_app_views(self) -> None:
        window = self.window()
        refresh = getattr(window, "refresh_library_views", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh_library()

    def _play_all(self) -> None:
        playable = [t for t in self._tracks if Path(t.file_path).exists()]
        if playable:
            self._engine.open_files(playable, autoplay=True)

    def _shuffle_all(self) -> None:
        playable = [t for t in self._tracks if Path(t.file_path).exists()]
        if playable:
            shuffled = list(playable)
            random.shuffle(shuffled)
            self._engine.open_files(shuffled, autoplay=True)

    def _play_selected(self) -> None:
        tracks = self._selected_tracks()
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if playable:
            self._engine.open_files(playable, autoplay=True)

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isRowSelected(
            index.row(), self.table.rootIndex()
        ):
            self.table.selectRow(index.row())
        tracks = self._selected_tracks()
        if not tracks:
            return
        menu = QMenu(self.table)
        play_action = menu.addAction("Play Now")
        play_next_action = menu.addAction("Play Next")
        add_queue_action = menu.addAction("Add to Queue")
        remove_fav_action = menu.addAction("Remove from favorites")
        playlist_menu = menu.addMenu("Add to playlist")
        playlists = []
        try:
            playlists = self._db.get_playlists()
        except Exception:
            playlists = []
        playlist_actions = {}
        for pl in playlists:
            act = playlist_menu.addAction(pl.name)
            playlist_actions[act] = pl.id
        playlist_menu.addSeparator()
        create_playlist_action = playlist_menu.addAction("Create new playlist...")
        menu.addSeparator()
        info_action = menu.addAction("Show track information")
        info_action.setEnabled(len(tracks) == 1)
        open_folder_action = menu.addAction("Open containing folder")
        open_folder_action.setEnabled(len(tracks) == 1)
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if chosen == play_action:
            self._play_selected()
        elif chosen == play_next_action:
            self._engine.play_next_files(playable)
        elif chosen == add_queue_action:
            self._engine.enqueue_files(playable)
        elif chosen == remove_fav_action:
            for t in tracks:
                try:
                    self._db.remove_favorite(t.id)
                except Exception:
                    pass
            self._refresh_app_views()
        elif chosen in playlist_actions:
            pid = playlist_actions[chosen]
            added = 0
            for t in tracks:
                try:
                    if self._db.add_track_to_playlist(pid, t.id):
                        added += 1
                except Exception:
                    pass
            if added == 0:
                QMessageBox.information(
                    self,
                    "Add to playlist",
                    "All selected tracks are already in that playlist.",
                )
            self._refresh_app_views()
        elif chosen == create_playlist_action:
            dialog = PlaylistDialog(self, title="Create Playlist", confirm_label="Create")
            if dialog.exec() == dialog.DialogCode.Accepted:
                name, desc = dialog.values()
                try:
                    pid = self._db.create_playlist(name, desc)
                    for t in tracks:
                        try:
                            self._db.add_track_to_playlist(pid, t.id)
                        except Exception:
                            pass
                except Exception as exc:
                    QMessageBox.warning(self, "Create playlist", str(exc))
                self._refresh_app_views()
        elif chosen == info_action:
            TrackInfoDialog(tracks[0], self).exec()
        elif chosen == open_folder_action:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(tracks[0].file_path).parent))
            )

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.search_field.refresh_theme(colors)
        self.sort_combo.refresh_theme(colors)
        self.empty_state.refresh_theme(colors)
