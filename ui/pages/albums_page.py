"""Albums page: album grid and album detail view."""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices
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
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase, TrackRecord
from ui.components.album_card import AlbumCard
from ui.components.card_grid import CardGrid
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
    "Track count": "track_count",
}


class AlbumsPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Albums", "Browse your collection by album.", parent=parent)
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self._albums: list[dict] = []
        self._album_tracks: list[TrackRecord] = []
        self._sort_descending = False
        self._current_album: dict | None = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.refresh_library)

        toolbar = QFrame(self)
        toolbar.setObjectName("toolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(10)
        self.search_field = SearchField("Search albums or artists", toolbar)
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
        self.sort_dir_button.setMinimumWidth(56)
        self.sort_dir_button.clicked.connect(self._toggle_sort_direction)
        tb.addWidget(self.sort_dir_button)
        self.count_label = QLabel("0 albums", toolbar)
        self.count_label.setObjectName("countLabel")
        tb.addWidget(self.count_label)
        self.body.addWidget(toolbar)

        self.grid_container = QWidget(self)
        grid_layout = QVBoxLayout(self.grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(0)
        self.album_grid = CardGrid(card_width=184, spacing=18, parent=self.grid_container)
        self.album_grid.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid_layout.addWidget(self.album_grid, 1)
        self.grid_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.grid_container, 1)

        self.detail_container = QWidget(self)
        self.detail_container.setVisible(False)
        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        detail_header = QHBoxLayout()
        detail_header.setSpacing(10)
        self.back_button = QPushButton("Back to albums", self.detail_container)
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.show_grid)
        detail_header.addWidget(self.back_button)
        self.detail_title = QLabel("", self.detail_container)
        self.detail_title.setObjectName("sectionTitle")
        detail_header.addWidget(self.detail_title, 1)
        self.play_album_button = QPushButton("Play album", self.detail_container)
        self.play_album_button.setObjectName("primaryButton")
        self.play_album_button.clicked.connect(self._play_current_album)
        detail_header.addWidget(self.play_album_button)
        self.shuffle_album_button = QPushButton("Shuffle", self.detail_container)
        self.shuffle_album_button.setObjectName("secondaryButton")
        self.shuffle_album_button.clicked.connect(self._shuffle_current_album)
        detail_header.addWidget(self.shuffle_album_button)
        self.add_album_queue_button = QPushButton("Add to queue", self.detail_container)
        self.add_album_queue_button.setObjectName("secondaryButton")
        self.add_album_queue_button.clicked.connect(self._add_current_album_to_queue)
        detail_header.addWidget(self.add_album_queue_button)
        detail_layout.addLayout(detail_header)

        self.detail_table = QTableWidget(0, 5, self.detail_container)
        self.detail_table.setObjectName("songsTable")
        self.detail_table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Duration", "Format"])
        self.detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.detail_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.setShowGrid(False)
        self.detail_table.verticalHeader().setVisible(False)
        configure_track_table(self.detail_table)
        self.detail_table.setWordWrap(False)
        self.detail_table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.detail_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.detail_table.customContextMenuRequested.connect(self._show_track_menu)
        self.detail_table.doubleClicked.connect(self._play_selected_detail_tracks)
        header = self.detail_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.detail_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout.addWidget(self.detail_table, 1)
        self.detail_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.detail_container, 1)

        self.empty_state = EmptyState(
            "albums",
            "No albums yet",
            "Albums from your imported music will appear here.",
            parent=self,
        )
        self.empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.empty_state, 1)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    def _toggle_sort_direction(self) -> None:
        self._sort_descending = not self._sort_descending
        self.sort_dir_button.setText("Desc" if self._sort_descending else "Asc")
        self.refresh_library()

    def refresh_library(self) -> None:
        query = self.search_field.text().strip()
        sort_by = SORT_MAP.get(self.sort_combo.currentText(), "title")
        try:
            self._albums = self._db.get_albums(query=query, sort_by=sort_by, descending=self._sort_descending)
        except Exception:
            self._albums = []
        self.album_grid.clear()
        for album in self._albums:
            title = str(album.get("album") or "Unknown Album")
            artist = str(album.get("album_artist") or "Unknown Artist")
            count = int(album.get("track_count") or 0)
            subtitle = f"{artist} • {count} track{'s' if count != 1 else ''}"
            card = AlbumCard(title=title, subtitle=subtitle, artwork_path=album.get("artwork_path"), payload=album, parent=self.album_grid)
            card.clicked.connect(self._show_album_detail)
            card.double_clicked.connect(self._play_album)
            card.refresh_theme(self._theme_manager.colors)
            self.album_grid.add_card(card)
        count = len(self._albums)
        noun = "album" if count == 1 else "albums"
        self.count_label.setText(f"{count} matching {noun}" if query else f"{count} {noun}")
        has = count > 0
        showing_detail = self._current_album is not None and has
        self.grid_container.setVisible(has and not showing_detail)
        self.detail_container.setVisible(showing_detail)
        self.empty_state.setVisible(not has)
        if not has and query:
            self.empty_state.set_message("No matching albums", "Try a different search term or clear the search field.")
        elif not has:
            self.empty_state.set_message("No albums yet", "Albums from your imported music will appear here.")
        if showing_detail:
            self._reload_current_album()

    def show_grid(self) -> None:
        self._current_album = None
        self.detail_container.setVisible(False)
        self.grid_container.setVisible(bool(self._albums))
        self.empty_state.setVisible(not self._albums)

    def _show_album_detail(self, card: AlbumCard) -> None:
        album = dict(card.payload or {})
        self._current_album = album
        self._reload_current_album()
        self.grid_container.setVisible(False)
        self.empty_state.setVisible(False)
        self.detail_container.setVisible(True)

    def _reload_current_album(self) -> None:
        album = self._current_album or {}
        album_name = str(album.get("album") or "")
        album_artist = str(album.get("album_artist") or "")
        self.detail_title.setText(f"{album_name} — {album_artist}")
        try:
            self._album_tracks = self._db.get_album_tracks(album_name, album_artist)
        except Exception:
            self._album_tracks = []
        fav_ids = set()
        try:
            fav_ids = {t.id for t in self._album_tracks if self._db.is_favorite(t.id)}
        except Exception:
            fav_ids = set()
        self.detail_table.setRowCount(len(self._album_tracks))
        for row, track in enumerate(self._album_tracks):
            row_no = str(track.track_number) if track.track_number else str(row + 1)
            if track.id in fav_ids:
                row_no = f"♥ {row_no}"
            values = [row_no, track.title, track.artist, format_time(track.duration), track.format.upper()]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.UserRole, track.file_path)
                if col == 0 and track.id in fav_ids:
                    item.setForeground(QColor(self._theme_manager.colors.accent))
                self.detail_table.setItem(row, col, item)
            decorate_track_row(self.detail_table, row, 1, track)

    def _play_album(self, card: AlbumCard) -> None:
        payload = card.payload or {}
        album = str(payload.get("album") or "")
        album_artist = str(payload.get("album_artist") or "")
        try:
            tracks = self._db.get_album_tracks(album, album_artist)
        except Exception:
            return
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if playable:
            self._engine.open_files(playable, autoplay=True)

    def _play_current_album(self) -> None:
        playable = [t for t in self._album_tracks if Path(t.file_path).exists()]
        if playable:
            self._engine.open_files(playable, autoplay=True)

    def _shuffle_current_album(self) -> None:
        playable = [t for t in self._album_tracks if Path(t.file_path).exists()]
        if playable:
            shuffled = list(playable)
            random.shuffle(shuffled)
            self._engine.open_files(shuffled, autoplay=True)

    def _add_current_album_to_queue(self) -> None:
        playable = [t for t in self._album_tracks if Path(t.file_path).exists()]
        if playable:
            self._engine.enqueue_files(playable)

    def _detail_selected_tracks(self) -> list[TrackRecord]:
        tracks = []
        for idx in self.detail_table.selectionModel().selectedRows():
            row = idx.row()
            if 0 <= row < len(self._album_tracks):
                tracks.append(self._album_tracks[row])
        return tracks

    def _play_selected_detail_tracks(self) -> None:
        tracks = self._detail_selected_tracks()
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if playable:
            self._engine.open_files(playable, autoplay=True)

    def _refresh_app_views(self) -> None:
        window = self.window()
        refresh = getattr(window, "refresh_library_views", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh_library()

    def _show_track_menu(self, pos) -> None:
        index = self.detail_table.indexAt(pos)
        if index.isValid() and not self.detail_table.selectionModel().isRowSelected(index.row(), self.detail_table.rootIndex()):
            self.detail_table.selectRow(index.row())
        tracks = self._detail_selected_tracks()
        if not tracks:
            return
        menu = QMenu(self.detail_table)
        play_action = menu.addAction("Play Now")
        play_next_action = menu.addAction("Play Next")
        add_queue_action = menu.addAction("Add to Queue")
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
        fav_action = None
        if len(tracks) == 1:
            try:
                is_fav = self._db.is_favorite(tracks[0].id)
            except Exception:
                is_fav = False
            fav_action = menu.addAction("Remove from favorites" if is_fav else "Add to favorites")
        menu.addSeparator()
        info_action = menu.addAction("Show track information")
        info_action.setEnabled(len(tracks) == 1)
        open_folder_action = menu.addAction("Open containing folder")
        open_folder_action.setEnabled(len(tracks) == 1)
        chosen = menu.exec(self.detail_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if chosen == play_action:
            if playable:
                self._engine.open_files(playable, autoplay=True)
        elif chosen == play_next_action:
            self._engine.play_next_files(playable)
        elif chosen == add_queue_action:
            self._engine.enqueue_files(playable)
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
                QMessageBox.information(self, "Add to playlist", "All selected tracks are already in that playlist.")
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
        elif fav_action is not None and chosen == fav_action:
            try:
                self._db.toggle_favorite(tracks[0].id)
            except Exception:
                pass
            self._refresh_app_views()
        elif chosen == info_action:
            TrackInfoDialog(tracks[0], self).exec()
        elif chosen == open_folder_action:
            folder = Path(tracks[0].file_path).parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.search_field.refresh_theme(colors)
        self.sort_combo.refresh_theme(colors)
        self.empty_state.refresh_theme(colors)
        for card in self.album_grid.findChildren(AlbumCard):
            card.refresh_theme(colors)
