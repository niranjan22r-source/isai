"""Atmospheric Home: a real-library starting point, not a dashboard."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import DARK, ThemeColors, ThemeManager
from services.ambient_palette import ambient_gradient_qss, ambient_service
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase, TrackRecord
from ui.components.empty_state import EmptyState
from ui.components.section_header import SectionHeader
from ui.components.track_shelf import TrackShelf
from ui.pages.base_page import BasePage


class HomePage(BasePage):
    """An artwork-led welcome, recent shelves, and a favorite shelf."""

    def __init__(
        self,
        theme_manager: ThemeManager,
        navigate: Callable[[str], None],
        library_db: LibraryDatabase,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Welcome to ISAI",
            "Your music. Your space.",
            parent=parent,
        )
        self._navigate = navigate
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self._sections: dict[str, dict] = {}
        self._hero_artwork: str | None = None
        self._ambient = ambient_service()
        self._ambient.palette_ready.connect(self._on_ambient_ready)

        self._build_hero()
        self._add_shelf(
            "recent",
            "Recently played",
            "recent",
            "recent",
            "Nothing played yet",
            "Tracks you listen to will gather here.",
        )
        self._add_shelf(
            "added",
            "Recently added",
            "songs",
            "songs",
            "No music added yet",
            "Import a music folder or audio files to build your library.",
        )
        self._add_shelf(
            "favorites",
            "Favorite music",
            "favorites",
            "favorites",
            "No favorites yet",
            "Songs you mark with a heart will appear here.",
        )
        self.body.addStretch(1)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    # ------------------------------------------------------------------- hero

    def _build_hero(self) -> None:
        self.hero = QFrame(self)
        self.hero.setObjectName("heroPanel")
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(30, 28, 30, 28)
        hero_layout.setSpacing(28)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(6)
        self.greeting_label = QLabel(self._greeting(), self.hero)
        self.greeting_label.setObjectName("heroEyebrow")
        text.addWidget(self.greeting_label)

        self.hero_title = QLabel("Your music, beautifully at home.", self.hero)
        self.hero_title.setObjectName("heroTitle")
        self.hero_title.setWordWrap(True)
        text.addWidget(self.hero_title)

        self.hero_subtitle = QLabel(
            "A calm, premium space for the music you already love.",
            self.hero,
        )
        self.hero_subtitle.setObjectName("heroSubtitle")
        self.hero_subtitle.setWordWrap(True)
        text.addWidget(self.hero_subtitle)

        stats = QHBoxLayout()
        stats.setContentsMargins(0, 14, 0, 0)
        stats.setSpacing(34)
        self.song_stat = self._stat("0", "songs", stats)
        self.favorite_stat = self._stat("0", "favorites", stats)
        self.playlist_stat = self._stat("0", "playlists", stats)
        stats.addStretch(1)
        text.addLayout(stats)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 14, 0, 0)
        actions.setSpacing(10)
        self.library_button = QPushButton("Browse Library", self.hero)
        self.library_button.setObjectName("primaryButton")
        self.library_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.library_button.clicked.connect(lambda: self._navigate("songs"))
        self.now_button = QPushButton("Now Playing", self.hero)
        self.now_button.setObjectName("secondaryButton")
        self.now_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.now_button.clicked.connect(lambda: self._navigate("now_playing"))
        actions.addWidget(self.library_button)
        actions.addWidget(self.now_button)
        actions.addStretch(1)
        text.addLayout(actions)

        hero_layout.addLayout(text, 1)
        self.body.addWidget(self.hero)

    def _stat(self, value: str, label: str, layout: QHBoxLayout) -> QLabel:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        value_label = QLabel(value)
        value_label.setObjectName("heroStatValue")
        name_label = QLabel(label)
        name_label.setObjectName("heroStatLabel")
        box.addWidget(value_label)
        box.addWidget(name_label)
        layout.addLayout(box)
        return value_label

    @staticmethod
    def _greeting() -> str:
        hour = datetime.now().hour
        if hour < 12:
            return "GOOD MORNING"
        if hour < 18:
            return "GOOD AFTERNOON"
        return "GOOD EVENING"

    # --------------------------------------------------------------- shelves

    def _add_shelf(
        self,
        key: str,
        title: str,
        target: str,
        icon_name: str,
        empty_title: str,
        description: str,
    ) -> None:
        section = QWidget(self)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = SectionHeader(title, "View all", section)
        header.action_clicked.connect(lambda t=target: self._navigate(t))
        layout.addWidget(header)

        empty = EmptyState(
            icon_name,
            empty_title,
            description,
            compact=True,
            parent=section,
        )
        layout.addWidget(empty)

        shelf = TrackShelf(on_play=self._play_shelf, parent=section)
        shelf.setVisible(False)
        layout.addWidget(shelf)

        self._sections[key] = {
            "empty": empty,
            "shelf": shelf,
            "tracks": [],
        }
        self.body.addWidget(section)

    def refresh_library(self) -> None:
        try:
            recently_played = self._db.get_recently_played(limit=10)
        except Exception:
            recently_played = []
        try:
            recently_added = self._db.get_recently_added(limit=10)
        except Exception:
            recently_added = []
        try:
            favorites = self._db.get_favorites()[:10]
        except Exception:
            favorites = []
        self._set_shelf_tracks("recent", recently_played)
        self._set_shelf_tracks("added", recently_added)
        self._set_shelf_tracks("favorites", favorites)

        try:
            song_count = self._db.track_count()
            favorite_count = self._db.get_favorite_count()
            playlist_count = len(self._db.get_playlists())
        except Exception:
            song_count = favorite_count = playlist_count = 0
        self.song_stat.setText(str(song_count))
        self.favorite_stat.setText(str(favorite_count))
        self.playlist_stat.setText(str(playlist_count))

        self._hero_artwork = recently_played[0].artwork_path if recently_played else None
        self._apply_hero_ambient()

    def _set_shelf_tracks(self, key: str, tracks: list[TrackRecord]) -> None:
        section = self._sections[key]
        section["tracks"] = tracks
        shelf: TrackShelf = section["shelf"]
        empty: EmptyState = section["empty"]
        shelf.set_tracks(tracks)
        has = bool(tracks)
        shelf.setVisible(has)
        empty.setVisible(not has)

    def _play_shelf(self, tracks: list[TrackRecord], start: int) -> None:
        paths = [t.file_path for t in tracks[start:] if Path(t.file_path).exists()]
        if paths:
            self._engine.open_files(paths, autoplay=True)

    # --------------------------------------------------------------- ambience

    def _apply_hero_ambient(self) -> None:
        colors = self._theme_manager.colors
        palette = self._ambient.cached(self._hero_artwork)
        if palette is None and self._hero_artwork:
            self._ambient.request(self._hero_artwork)
        dark = self._theme_manager.effective_theme == DARK
        gradient = ambient_gradient_qss(
            palette,
            dark=dark,
            base=colors.bg_soft,
            fallback_glow=colors.ambient,
        )
        self.hero.setStyleSheet(
            "QFrame#heroPanel { background: %s; border: 1px solid %s; "
            "border-radius: 20px; }" % (gradient, colors.border)
        )

    def _on_ambient_ready(self, path: str, _palette: object) -> None:
        if path == self._hero_artwork:
            self._apply_hero_ambient()

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.greeting_label.setText(self._greeting())
        for child in self.findChildren(EmptyState):
            child.refresh_theme(colors)
        for child in self.findChildren(TrackShelf):
            child.refresh_theme(colors)
        self._apply_hero_ambient()
