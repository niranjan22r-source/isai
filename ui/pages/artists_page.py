"""Artists page: artist grid from the library database."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from core.theme_manager import ThemeColors, ThemeManager
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase
from ui.components.artist_card import ArtistCard
from ui.components.card_grid import CardGrid
from ui.components.empty_state import EmptyState
from ui.components.search_field import SearchField
from ui.components.sort_combo import SortComboBox
from ui.pages.base_page import BasePage

SORT_MAP = {
    "Name": "name",
    "Track count": "track_count",
    "Album count": "album_count",
}


class ArtistsPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        navigate: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Artists", "The people behind your music.", parent=parent)
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self._navigate = navigate
        self._songs_page = None
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
        self.search_field = SearchField("Search artists", toolbar)
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
        self.count_label = QLabel("0 artists", toolbar)
        self.count_label.setObjectName("countLabel")
        tb.addWidget(self.count_label)
        self.body.addWidget(toolbar)

        self.artist_grid = CardGrid(card_width=148, spacing=18, parent=self)
        self.artist_grid.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.artist_grid, 1)

        self.empty_state = EmptyState(
            "artists",
            "No artists yet",
            "Artists from your imported music will appear here.",
            parent=self,
        )
        self.empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.empty_state, 1)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    def set_songs_page(self, songs_page) -> None:
        self._songs_page = songs_page

    def _toggle_sort_direction(self) -> None:
        self._sort_descending = not self._sort_descending
        self.sort_dir_button.setText("Desc" if self._sort_descending else "Asc")
        self.refresh_library()

    def refresh_library(self) -> None:
        query = self.search_field.text().strip()
        sort_by = SORT_MAP.get(self.sort_combo.currentText(), "name")
        try:
            artists = self._db.get_artists(query=query, sort_by=sort_by, descending=self._sort_descending)
        except Exception:
            artists = []
        self.artist_grid.clear()
        for artist in artists:
            name = str(artist.get("artist") or "Unknown Artist")
            track_count = int(artist.get("track_count") or 0)
            album_count = int(artist.get("album_count") or 0)
            subtitle = f"{album_count} album{'s' if album_count != 1 else ''} • {track_count} track{'s' if track_count != 1 else ''}"
            card = ArtistCard(name=name, subtitle=subtitle, payload=artist, parent=self.artist_grid)
            card.clicked.connect(self._open_artist)
            card.refresh_theme(self._theme_manager.colors)
            self.artist_grid.add_card(card)

        count = len(artists)
        noun = "artist" if count == 1 else "artists"
        self.count_label.setText(f"{count} matching {noun}" if query else f"{count} {noun}")
        has = count > 0
        self.artist_grid.setVisible(has)
        self.empty_state.setVisible(not has)
        if not has and query:
            self.empty_state.set_message("No matching artists", "Try a different search term or clear the search field.")
        elif not has:
            self.empty_state.set_message("No artists yet", "Artists from your imported music will appear here.")

    def _open_artist(self, card: ArtistCard) -> None:
        payload = card.payload or {}
        name = str(payload.get("artist") or "")
        if self._songs_page is not None and hasattr(self._songs_page, "filter_by_artist"):
            self._songs_page.filter_by_artist(name)
        self._navigate("songs")

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.search_field.refresh_theme(colors)
        self.sort_combo.refresh_theme(colors)
        self.empty_state.refresh_theme(colors)
        for card in self.artist_grid.findChildren(ArtistCard):
            card.refresh_theme(colors)
