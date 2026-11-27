"""Songs page: searchable, sortable library track list."""

from __future__ import annotations

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
    "Date added": "date_added",
}


class SongsPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Songs",
            "Every track in your library.",
            parent=parent,
        )
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
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)

        self.search_field = SearchField("Search title, artist, or album", toolbar)
        self.search_field.setFixedHeight(38)
        self.search_field.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.search_field, 1)

        self.sort_combo = SortComboBox(toolbar)
        self.sort_combo.setAccessibleName("Sort songs")
        self.sort_combo.setToolTip("Sort songs")
        self.sort_combo.addItems(list(SORT_MAP.keys()))
        self.sort_combo.setFixedHeight(38)
        self.sort_combo.currentTextChanged.connect(self.refresh_library)
        toolbar_layout.addWidget(self.sort_combo)

        self.sort_dir_button = QPushButton("Asc", toolbar)
        self.sort_dir_button.setObjectName("sortDirButton")
        self.sort_dir_button.setFixedHeight(38)
        self.sort_dir_button.setMinimumWidth(56)
        self.sort_dir_button.setToolTip("Toggle ascending/descending sort")
        self.sort_dir_button.clicked.connect(self._toggle_sort_direction)
        toolbar_layout.addWidget(self.sort_dir_button)

        self.count_label = QLabel("0 songs", toolbar)
        self.count_label.setObjectName("countLabel")
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.count_label.setMinimumWidth(90)
        toolbar_layout.addWidget(self.count_label)

        self.body.addWidget(toolbar)

        self.table = QTableWidget(0, 6, self)
        self.table.setObjectName("songsTable")
        self.table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Album", "Duration", "Format"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        configure_track_table(self.table)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._play_from_row)
        self.table.setMinimumHeight(300)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "songs",
            "Your library is empty",
            "Import a music folder or audio files to start building your library.",
            parent=self,
        )
        self.empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.empty_state, 1)
        self._update_sort_dir_label()
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    def filter_by_artist(self, artist: str) -> None:
        self.search_field.setText(artist)

    def _on_search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _toggle_sort_direction(self) -> None:
        self._sort_descending = not self._sort_descending
        self._update_sort_dir_label()
        self.refresh_library()

    def _update_sort_dir_label(self) -> None:
        self.sort_dir_button.setText("Desc" if self._sort_descending else "Asc")

    def refresh_library(self) -> None:
        selected_paths = {
            t.file_path for t in self._selected_tracks()
        }
        query = self.search_field.text().strip()
        order_by = SORT_MAP.get(self.sort_combo.currentText(), "title")
        try:
            if query:
                self._tracks = self._db.search_tracks(
                    query, order_by=order_by, descending=self._sort_descending
                )
            else:
                self._tracks = self._db.get_all_tracks(
                    order_by=order_by, descending=self._sort_descending
                )
        except Exception:
            self._tracks = []

        fav_ids = set()
        try:
            for t in self._tracks:
                if self._db.is_favorite(t.id):
                    fav_ids.add(t.id)
        except Exception:
            fav_ids = set()

        self.table.setRowCount(len(self._tracks))
        for row_idx, track in enumerate(self._tracks):
            row_no = str(track.track_number) if track.track_number else str(row_idx + 1)
            if track.id in fav_ids:
                row_no = f"♥ {row_no}"
            values = [
                row_no,
                track.title,
                track.artist,
                track.album,
                format_time(track.duration),
                track.format.upper(),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.UserRole, track.file_path)
                if col == 0 and track.id in fav_ids:
                    item.setForeground(QColor(self._theme_manager.colors.accent))
                self.table.setItem(row_idx, col, item)
            decorate_track_row(self.table, row_idx, 1, track)
            if track.file_path in selected_paths:
                self.table.selectRow(row_idx)

        count = len(self._tracks)
        noun = "song" if count == 1 else "songs"
        if query:
            self.count_label.setText(f"{count} matching {noun}")
        else:
            self.count_label.setText(f"{count} {noun}")
        has_tracks = count > 0
        self.table.setVisible(has_tracks)
        self.empty_state.setVisible(not has_tracks)
        if not has_tracks and query:
            self.empty_state.set_message(
                "No matching songs",
                "Try a different search term or clear the search field.",
            )
        elif not has_tracks:
            self.empty_state.set_message(
                "Your library is empty",
                "Import a music folder or audio files to start building your library.",
            )

    def _selected_tracks(self) -> list[TrackRecord]:
        seen: set[int] = set()
        tracks: list[TrackRecord] = []
        for idx in self.table.selectionModel().selectedRows():
            row = idx.row()
            if 0 <= row < len(self._tracks) and row not in seen:
                seen.add(row)
                tracks.append(self._tracks[row])
        return tracks

    def _track_at_row(self, row: int) -> TrackRecord | None:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def _refresh_app_views(self) -> None:
        window = self.window()
        refresh = getattr(window, "refresh_library_views", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh_library()

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if index.isValid() and not self.table.selectionModel().isRowSelected(index.row(), self.table.rootIndex()):
            self.table.selectRow(index.row())
        tracks = self._selected_tracks()
        if not tracks:
            return
        menu = QMenu(self.table)
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
            fav_action = menu.addAction("Remove from Favorites" if is_fav else "Add to Favorites")

        menu.addSeparator()
        info_action = menu.addAction("Show Track Information")
        open_folder_action = menu.addAction("Open containing folder")
        info_action.setEnabled(len(tracks) == 1)
        open_folder_action.setEnabled(len(tracks) == 1)

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if chosen == play_action:
            self._play_tracks(tracks)
        elif chosen == play_next_action:
            self._engine.play_next_files(playable)
        elif chosen == add_queue_action:
            self._engine.enqueue_files(playable)
        elif chosen in playlist_actions:
            self._add_tracks_to_playlist(playlist_actions[chosen], tracks)
        elif chosen == create_playlist_action:
            self._create_playlist_and_add(tracks)
        elif fav_action is not None and chosen == fav_action:
            self._toggle_favorite(tracks[0])
        elif chosen == info_action:
            self._show_track_info(tracks[0])
        elif chosen == open_folder_action:
            self._open_containing_folder(tracks[0])

    def _add_tracks_to_playlist(self, playlist_id: int, tracks: list[TrackRecord]) -> None:
        added = 0
        for t in tracks:
            try:
                if self._db.add_track_to_playlist(playlist_id, t.id):
                    added += 1
            except Exception:
                pass
        if added == 0:
            QMessageBox.information(self, "Add to playlist", "All selected tracks are already in that playlist.")
        self._refresh_app_views()

    def _create_playlist_and_add(self, tracks: list[TrackRecord]) -> None:
        dialog = PlaylistDialog(self, title="Create Playlist", confirm_label="Create")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        name, desc = dialog.values()
        try:
            pid = self._db.create_playlist(name, desc)
        except Exception as exc:
            QMessageBox.warning(self, "Create playlist", str(exc))
            return
        self._add_tracks_to_playlist(pid, tracks)

    def _toggle_favorite(self, track: TrackRecord) -> None:
        try:
            self._db.toggle_favorite(track.id)
        except Exception:
            return
        self._refresh_app_views()

    def _play_selected(self) -> None:
        tracks = self._selected_tracks()
        if tracks:
            self._play_tracks(tracks)

    def _play_from_row(self, index) -> None:
        row = index.row()
        if row < 0 or row >= len(self._tracks):
            return
        # Play all visible songs, starting at the clicked track. Track records
        # travel with the queue so metadata survives beyond the table.
        playable = [t for t in self._tracks if Path(t.file_path).exists()]
        if not playable:
            return
        start_path = self._tracks[row].file_path
        start_index = 0
        for i, track in enumerate(playable):
            if track.file_path == start_path:
                start_index = i
                break
        self._engine.open_files(playable, autoplay=True, start_index=start_index)

    def _play_tracks(self, tracks: list[TrackRecord]) -> None:
        if not tracks:
            return
        playable = [t for t in tracks if Path(t.file_path).exists()]
        if not playable:
            return
        self._engine.open_files(playable, autoplay=True)

    def _show_track_info(self, track: TrackRecord) -> None:
        dialog = TrackInfoDialog(track, self)
        dialog.exec()

    @staticmethod
    def _open_containing_folder(track: TrackRecord) -> None:
        path = Path(track.file_path)
        folder = path.parent if path.parent.exists() else path
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.search_field.refresh_theme(colors)
        self.sort_combo.refresh_theme(colors)
        self.empty_state.refresh_theme(colors)
