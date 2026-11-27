"""Playlists page: create, manage, and play playlists."""

from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from ui.components.empty_state import EmptyState
from ui.components.playlist_dialog import PlaylistDialog
from ui.components.search_field import SearchField
from ui.components.track_info_dialog import TrackInfoDialog
from ui.components.track_table import configure_track_table, decorate_track_row
from ui.pages.base_page import BasePage
from ui.player_bar import format_time


class AddTracksDialog(QDialog):
    def __init__(self, db: LibraryDatabase, existing_ids: set[int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Tracks to Playlist")
        self.setModal(True)
        self.resize(700, 480)
        self._db = db
        self._existing_ids = existing_ids
        self._tracks: list[TrackRecord] = []

        layout = QVBoxLayout(self)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search tracks...")
        self.search.textChanged.connect(self._reload)
        layout.addWidget(self.search)

        self.list = QListWidget(self)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self.add_btn = buttons.addButton("Add selected", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._reload()

    def _reload(self) -> None:
        q = self.search.text().strip()
        try:
            tracks = self._db.search_tracks(q, order_by="title") if q else self._db.get_all_tracks(order_by="title")
        except Exception:
            tracks = []
        self._tracks = [t for t in tracks if t.id not in self._existing_ids]
        self.list.clear()
        for t in self._tracks:
            item = QListWidgetItem(f"{t.title} — {t.artist} ({t.album})")
            item.setData(Qt.ItemDataRole.UserRole, t.id)
            item.setToolTip(t.file_path)
            self.list.addItem(item)

    def selected_track_ids(self) -> list[int]:
        ids = []
        for item in self.list.selectedItems():
            tid = item.data(Qt.ItemDataRole.UserRole)
            if tid is not None:
                ids.append(int(tid))
        return ids


class PlaylistsPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        create_button = QPushButton("Create playlist")
        create_button.setObjectName("primaryButton")
        create_button.clicked.connect(self._create_playlist)

        super().__init__("Playlists", "Your collections, your way.", action=create_button, parent=parent)
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self.create_playlist_button = create_button
        self._playlists = []
        self._current_playlist = None
        self._playlist_tracks: list[TrackRecord] = []

        # List view
        self.list_container = QWidget(self)
        list_layout = QVBoxLayout(self.list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        toolbar = QFrame(self.list_container)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(10)
        self.search_field = SearchField("Search playlists", toolbar)
        self.search_field.setFixedHeight(38)
        self.search_field.textChanged.connect(self.refresh_library)
        tb.addWidget(self.search_field, 1)
        self.count_label = QLabel("0 playlists", toolbar)
        self.count_label.setObjectName("countLabel")
        tb.addWidget(self.count_label)
        list_layout.addWidget(toolbar)

        self.playlist_table = QTableWidget(0, 3, self.list_container)
        self.playlist_table.setObjectName("songsTable")
        self.playlist_table.setHorizontalHeaderLabels(["Name", "Tracks", "Created"])
        self.playlist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.playlist_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.playlist_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.playlist_table.setShowGrid(False)
        self.playlist_table.verticalHeader().setVisible(False)
        self.playlist_table.doubleClicked.connect(self._open_selected_playlist)
        ph = self.playlist_table.horizontalHeader()
        ph.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        ph.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.playlist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_table.customContextMenuRequested.connect(self._playlist_context_menu)
        self.playlist_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        list_layout.addWidget(self.playlist_table, 1)
        self.list_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.list_container, 1)

        # Detail view
        self.detail_container = QWidget(self)
        self.detail_container.setVisible(False)
        detail_layout = QVBoxLayout(self.detail_container)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        header_row = QHBoxLayout()
        self.back_button = QPushButton("Back to playlists", self.detail_container)
        self.back_button.setObjectName("secondaryButton")
        self.back_button.clicked.connect(self.show_list)
        header_row.addWidget(self.back_button)
        self.detail_name = QLabel("", self.detail_container)
        self.detail_name.setObjectName("sectionTitle")
        header_row.addWidget(self.detail_name, 1)
        self.play_all_button = QPushButton("Play all", self.detail_container)
        self.play_all_button.setObjectName("primaryButton")
        self.play_all_button.clicked.connect(self._play_all)
        header_row.addWidget(self.play_all_button)
        self.shuffle_button = QPushButton("Shuffle", self.detail_container)
        self.shuffle_button.setObjectName("secondaryButton")
        self.shuffle_button.clicked.connect(self._shuffle_all)
        header_row.addWidget(self.shuffle_button)
        self.rename_button = QPushButton("Rename", self.detail_container)
        self.rename_button.setObjectName("secondaryButton")
        self.rename_button.clicked.connect(self._rename_current_playlist)
        header_row.addWidget(self.rename_button)
        self.delete_button = QPushButton("Delete", self.detail_container)
        self.delete_button.setObjectName("secondaryButton")
        self.delete_button.clicked.connect(self._delete_current_playlist)
        header_row.addWidget(self.delete_button)
        detail_layout.addLayout(header_row)

        self.detail_desc = QLabel("", self.detail_container)
        self.detail_desc.setObjectName("pageSubtitle")
        self.detail_desc.setWordWrap(True)
        detail_layout.addWidget(self.detail_desc)

        actions_row = QHBoxLayout()
        self.add_tracks_button = QPushButton("Add tracks", self.detail_container)
        self.add_tracks_button.setObjectName("secondaryButton")
        self.add_tracks_button.clicked.connect(self._add_tracks)
        actions_row.addWidget(self.add_tracks_button)
        self.remove_tracks_button = QPushButton("Remove selected", self.detail_container)
        self.remove_tracks_button.setObjectName("secondaryButton")
        self.remove_tracks_button.clicked.connect(self._remove_selected_tracks)
        actions_row.addWidget(self.remove_tracks_button)
        self.move_up_button = QPushButton("Move up", self.detail_container)
        self.move_up_button.setObjectName("secondaryButton")
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        actions_row.addWidget(self.move_up_button)
        self.move_down_button = QPushButton("Move down", self.detail_container)
        self.move_down_button.setObjectName("secondaryButton")
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        actions_row.addWidget(self.move_down_button)
        actions_row.addStretch(1)
        self.detail_count = QLabel("", self.detail_container)
        self.detail_count.setObjectName("countLabel")
        actions_row.addWidget(self.detail_count)
        detail_layout.addLayout(actions_row)

        self.track_table = QTableWidget(0, 5, self.detail_container)
        self.track_table.setObjectName("songsTable")
        self.track_table.setHorizontalHeaderLabels(["#", "Title", "Artist", "Album", "Duration"])
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.setShowGrid(False)
        self.track_table.verticalHeader().setVisible(False)
        configure_track_table(self.track_table)
        self.track_table.doubleClicked.connect(self._play_selected_track)
        self.track_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.track_table.customContextMenuRequested.connect(self._track_context_menu)
        th = self.track_table.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.track_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout.addWidget(self.track_table, 1)
        self.detail_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.detail_container, 1)

        self.empty_state = EmptyState(
            "playlists",
            "No playlists yet",
            "Create a playlist to organize your music.",
            parent=self,
        )
        self.empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.empty_state, 1)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    # ----------------------------------------------------------------- list

    def refresh_library(self) -> None:
        q = self.search_field.text().strip().lower()
        try:
            pls = self._db.get_playlists()
        except Exception:
            pls = []
        if q:
            pls = [p for p in pls if q in p.name.lower() or q in (p.description or "").lower()]
        self._playlists = pls
        self.playlist_table.setRowCount(len(pls))
        for row, pl in enumerate(pls):
            name_item = QTableWidgetItem(pl.name)
            name_item.setToolTip(pl.description or pl.name)
            name_item.setData(Qt.ItemDataRole.UserRole, pl.id)
            count_item = QTableWidgetItem(str(pl.track_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            created = (pl.date_created or "")[:10]
            created_item = QTableWidgetItem(created)
            self.playlist_table.setItem(row, 0, name_item)
            self.playlist_table.setItem(row, 1, count_item)
            self.playlist_table.setItem(row, 2, created_item)
        count = len(pls)
        self.count_label.setText(f"{count} playlist{'s' if count != 1 else ''}")
        has = count > 0
        showing_detail = self._current_playlist is not None
        self.list_container.setVisible(has and not showing_detail)
        self.detail_container.setVisible(showing_detail)
        self.empty_state.setVisible(not has and not showing_detail)
        if showing_detail:
            self._reload_detail()
        if not has and q:
            self.empty_state.set_message("No matching playlists", "Try a different search term.")
        elif not has:
            self.empty_state.set_message("No playlists yet", "Create a playlist to organize your music.")

    def _playlist_at_row(self, row: int):
        if 0 <= row < len(self._playlists):
            return self._playlists[row]
        return None

    def _open_selected_playlist(self) -> None:
        row = self.playlist_table.currentRow()
        pl = self._playlist_at_row(row)
        if pl is not None:
            self._open_playlist(pl.id)

    def _open_playlist(self, playlist_id: int) -> None:
        self._current_playlist = playlist_id
        self._reload_detail()
        self.list_container.setVisible(False)
        self.empty_state.setVisible(False)
        self.detail_container.setVisible(True)

    def show_list(self) -> None:
        self._current_playlist = None
        self.detail_container.setVisible(False)
        self.refresh_library()

    def _reload_detail(self) -> None:
        pid = self._current_playlist
        if pid is None:
            return
        try:
            pl = self._db.get_playlist(pid)
        except Exception:
            pl = None
        if pl is None:
            self.show_list()
            return
        self.detail_name.setText(pl.name)
        self.detail_desc.setText(pl.description or "")
        self.detail_desc.setVisible(bool(pl.description))
        try:
            self._playlist_tracks = self._db.get_playlist_tracks(pid)
        except Exception:
            self._playlist_tracks = []
        self.detail_count.setText(f"{len(self._playlist_tracks)} track{'s' if len(self._playlist_tracks) != 1 else ''}")
        fav_ids = set()
        try:
            fav_ids = {t.id for t in self._playlist_tracks if self._db.is_favorite(t.id)}
        except Exception:
            fav_ids = set()
        self.track_table.setRowCount(len(self._playlist_tracks))
        for row, t in enumerate(self._playlist_tracks):
            row_no = str(row + 1)
            if t.id in fav_ids:
                row_no = f"♥ {row_no}"
            values = [row_no, t.title, t.artist, t.album, format_time(t.duration)]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(value)
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                if col == 0 and t.id in fav_ids:
                    item.setForeground(QColor(self._theme_manager.colors.accent))
                self.track_table.setItem(row, col, item)
            decorate_track_row(self.track_table, row, 1, t)

    # ------------------------------------------------------------- actions

    def _create_playlist(self) -> None:
        dialog = PlaylistDialog(self, title="Create Playlist", confirm_label="Create")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        name, desc = dialog.values()
        try:
            pid = self._db.create_playlist(name, desc)
        except Exception as exc:
            QMessageBox.warning(self, "Create playlist", str(exc))
            return
        self._refresh_app_views()
        self._open_playlist(pid)

    def _rename_current_playlist(self) -> None:
        pid = self._current_playlist
        if pid is None:
            return
        pl = self._db.get_playlist(pid)
        if pl is None:
            return
        dialog = PlaylistDialog(self, title="Rename Playlist", name=pl.name, description=pl.description, confirm_label="Rename")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        name, desc = dialog.values()
        try:
            self._db.rename_playlist(pid, name)
            with self._db.connect() as conn:
                from services.library_database import utc_now_iso
                conn.execute(
                    "UPDATE playlists SET description = ?, date_modified = ? WHERE id = ?",
                    (desc, utc_now_iso(), pid),
                )
        except Exception as exc:
            QMessageBox.warning(self, "Rename playlist", str(exc))
            return
        self._refresh_app_views()

    def _delete_current_playlist(self) -> None:
        pid = self._current_playlist
        if pid is None:
            return
        pl = self._db.get_playlist(pid)
        if pl is None:
            return
        res = QMessageBox.question(
            self,
            "Delete playlist",
            f"Delete playlist '{pl.name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if res != QMessageBox.StandardButton.Yes:
            return
        try:
            self._db.delete_playlist(pid)
        except Exception as exc:
            QMessageBox.warning(self, "Delete playlist", str(exc))
            return
        self._current_playlist = None
        self._refresh_app_views()
        self.show_list()

    def _add_tracks(self) -> None:
        pid = self._current_playlist
        if pid is None:
            return
        existing = {t.id for t in self._playlist_tracks}
        dialog = AddTracksDialog(self._db, existing, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        ids = dialog.selected_track_ids()
        for tid in ids:
            try:
                self._db.add_track_to_playlist(pid, tid)
            except Exception:
                pass
        self._refresh_app_views()

    def _selected_detail_rows(self) -> list[int]:
        return sorted({idx.row() for idx in self.track_table.selectionModel().selectedRows()})

    def _remove_selected_tracks(self) -> None:
        pid = self._current_playlist
        if pid is None:
            return
        rows = self._selected_detail_rows()
        if not rows:
            return
        for row in reversed(rows):
            if 0 <= row < len(self._playlist_tracks):
                tid = self._playlist_tracks[row].id
                try:
                    self._db.remove_track_from_playlist(pid, tid)
                except Exception:
                    pass
        self._refresh_app_views()

    def _move_selected(self, delta: int) -> None:
        pid = self._current_playlist
        if pid is None:
            return
        rows = self._selected_detail_rows()
        if len(rows) != 1:
            return
        row = rows[0]
        new_row = row + delta
        if not (0 <= row < len(self._playlist_tracks) and 0 <= new_row < len(self._playlist_tracks)):
            return
        ordered = [t.id for t in self._playlist_tracks]
        ordered[row], ordered[new_row] = ordered[new_row], ordered[row]
        try:
            self._db.reorder_playlist_tracks(pid, ordered)
        except Exception as exc:
            QMessageBox.warning(self, "Reorder tracks", str(exc))
            return
        self._refresh_app_views()
        self.track_table.selectRow(new_row)

    def _play_all(self) -> None:
        playable = [t for t in self._playlist_tracks if Path(t.file_path).exists()]
        if not playable:
            QMessageBox.information(self, "Play playlist", "This playlist has no playable tracks.")
            return
        self._engine.open_files(playable, autoplay=True)

    def _shuffle_all(self) -> None:
        playable = [t for t in self._playlist_tracks if Path(t.file_path).exists()]
        if not playable:
            QMessageBox.information(self, "Play playlist", "This playlist has no playable tracks.")
            return
        shuffled = list(playable)
        random.shuffle(shuffled)
        self._engine.open_files(shuffled, autoplay=True)

    def _play_selected_track(self) -> None:
        rows = self._selected_detail_rows()
        if not rows:
            return
        start = rows[0]
        playable = [t for t in self._playlist_tracks[start:] if Path(t.file_path).exists()]
        if playable:
            self._engine.open_files(playable, autoplay=True)

    def _refresh_app_views(self) -> None:
        window = self.window()
        refresh = getattr(window, "refresh_library_views", None)
        if callable(refresh):
            refresh()
        else:
            self.refresh_library()

    def _playlist_context_menu(self, pos) -> None:
        index = self.playlist_table.indexAt(pos)
        if not index.isValid():
            return
        self.playlist_table.selectRow(index.row())
        pl = self._playlist_at_row(index.row())
        if pl is None:
            return
        menu = QMenu(self.playlist_table)
        open_action = menu.addAction("Open")
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self.playlist_table.viewport().mapToGlobal(pos))
        if chosen == open_action:
            self._open_playlist(pl.id)
        elif chosen == rename_action:
            self._current_playlist = pl.id
            self._rename_current_playlist()
        elif chosen == delete_action:
            self._current_playlist = pl.id
            self._delete_current_playlist()

    def _track_context_menu(self, pos) -> None:
        index = self.track_table.indexAt(pos)
        if index.isValid() and not self.track_table.selectionModel().isRowSelected(index.row(), self.track_table.rootIndex()):
            self.track_table.selectRow(index.row())
        rows = self._selected_detail_rows()
        if not rows:
            return
        tracks = [self._playlist_tracks[r] for r in rows if 0 <= r < len(self._playlist_tracks)]
        menu = QMenu(self.track_table)
        play_action = menu.addAction("Play Now")
        play_next_action = menu.addAction("Play Next")
        add_queue_action = menu.addAction("Add to Queue")
        remove_action = menu.addAction("Remove from playlist")
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
        chosen = menu.exec(self.track_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        playable_sel = [t for t in tracks if Path(t.file_path).exists()]
        if chosen == play_action:
            start = rows[0]
            playable = [t for t in self._playlist_tracks[start:] if Path(t.file_path).exists()]
            if playable:
                self._engine.open_files(playable, autoplay=True)
        elif chosen == play_next_action:
            self._engine.play_next_files(playable_sel)
        elif chosen == add_queue_action:
            self._engine.enqueue_files(playable_sel)
        elif chosen == remove_action:
            self._remove_selected_tracks()
        elif fav_action is not None and chosen == fav_action:
            try:
                self._db.toggle_favorite(tracks[0].id)
            except Exception:
                pass
            self._refresh_app_views()
        elif chosen == info_action:
            TrackInfoDialog(tracks[0], self).exec()
        elif chosen == open_folder_action:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(tracks[0].file_path).parent)))

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.search_field.refresh_theme(colors)
        self.empty_state.refresh_theme(colors)
