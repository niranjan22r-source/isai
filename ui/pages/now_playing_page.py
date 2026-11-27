"""Immersive Now Playing page with artwork-led ambience and embedded/local lyrics."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import DARK, ThemeColors, ThemeManager
from services.ambient_palette import ambient_gradient_qss, ambient_service
from services.audio_engine import AudioEngine, STATE_PLAYING
from services.lyrics_service import LyricsData, LyricsService
from ui.components.artwork import artwork_ready_connect, request_rounded_pixmap
from ui.icons import icon
from ui.pages.base_page import BasePage
from ui.player_bar import format_time

ARTWORK_SIZE = 360
ARTWORK_SMALL = 260


class NowPlayingPage(BasePage):
    def __init__(
        self,
        theme_manager: ThemeManager,
        library_db,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Now Playing",
            "An atmosphere for the track in the air.",
            parent=parent,
        )
        self._theme_manager = theme_manager
        self._db = library_db
        self._engine = audio_engine
        self._lyrics_service = LyricsService()
        self._lyrics: LyricsData | None = None
        self._explicit_lrc: str | None = None
        self._current_path: str | None = None
        self._current_artwork: str | None = None
        self._seeking = False
        self._colors = theme_manager.colors
        self._active_lyric_index = -1
        self._ambient = ambient_service()
        self._ambient.palette_ready.connect(self._on_ambient_ready)
        self._art_key = None
        artwork_ready_connect(self._on_artwork_ready)

        self.canvas = QFrame(self)
        self.canvas.setObjectName("nowPlayingCanvas")
        root = QVBoxLayout(self.canvas)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Centered content column
        self._content_wrap = QWidget(self.canvas)
        self._content_wrap.setMaximumWidth(920)
        self._content_wrap.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        content = QVBoxLayout(self._content_wrap)
        content.setContentsMargins(28, 24, 28, 32)
        content.setSpacing(14)

        self.artwork = QLabel(self._content_wrap)
        self.artwork.setObjectName("nowPlayingArtwork")
        self.artwork.setFixedSize(ARTWORK_SIZE, ARTWORK_SIZE)
        self.artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.artwork, 0, Qt.AlignmentFlag.AlignHCenter)

        self.eyebrow = QLabel("NOW PLAYING", self._content_wrap)
        self.eyebrow.setObjectName("nowPlayingEyebrow")
        self.eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.eyebrow)

        self.title_label = QLabel("No track playing", self._content_wrap)
        self.title_label.setObjectName("nowPlayingTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        self.artist_label = QLabel(
            "Select a song to start playback", self._content_wrap
        )
        self.artist_label.setObjectName("nowPlayingArtist")
        self.artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_label.setWordWrap(True)
        self.album_label = QLabel("", self._content_wrap)
        self.album_label.setObjectName("nowPlayingAlbum")
        self.album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_label.setWordWrap(True)
        content.addWidget(self.title_label)
        content.addWidget(self.artist_label)
        content.addWidget(self.album_label)

        # Progress
        prog = QHBoxLayout()
        prog.setContentsMargins(0, 10, 0, 0)
        prog.setSpacing(10)
        self.current_time = QLabel("0:00", self._content_wrap)
        self.current_time.setObjectName("playerTime")
        self.current_time.setFixedWidth(48)
        self.progress = QSlider(Qt.Orientation.Horizontal, self._content_wrap)
        self.progress.setObjectName("playerProgress")
        self.progress.setRange(0, 0)
        self.progress.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.progress.sliderReleased.connect(self._seek_released)
        self.progress.sliderMoved.connect(
            lambda v: self.current_time.setText(format_time(v))
        )
        self.duration_time = QLabel("0:00", self._content_wrap)
        self.duration_time.setObjectName("playerTime")
        self.duration_time.setFixedWidth(48)
        prog.addWidget(self.current_time)
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.duration_time)
        content.addLayout(prog)

        # Controls
        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.addStretch(1)
        self.shuffle_btn = self._btn("shuffle", "Shuffle")
        self.shuffle_btn.clicked.connect(self._engine.queue_manager.toggle_shuffle)
        self.prev_btn = self._btn("previous", "Previous")
        self.prev_btn.clicked.connect(self._engine.previous_track)
        self.play_btn = self._btn("play", "Play")
        self.play_btn.setObjectName("nowPlayingPlay")
        self.play_btn.setFixedSize(56, 56)
        self.play_btn.setIconSize(QSize(24, 24))
        self.play_btn.clicked.connect(self._engine.toggle_play_pause)
        self.next_btn = self._btn("next", "Next")
        self.next_btn.clicked.connect(self._engine.next_track)
        self.repeat_btn = self._btn("repeat", "Repeat")
        self.repeat_btn.clicked.connect(self._engine.queue_manager.cycle_repeat_mode)
        self.fav_btn = self._btn("favorites", "Favorite")
        self.fav_btn.clicked.connect(self._toggle_favorite)
        for button in (
            self.shuffle_btn,
            self.prev_btn,
            self.play_btn,
            self.next_btn,
            self.repeat_btn,
            self.fav_btn,
        ):
            controls.addWidget(button)
        controls.addStretch(1)
        content.addLayout(controls)

        # Volume and secondary actions
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.setContentsMargins(0, 0, 0, 0)
        self.vol_icon = self._btn("volume", "Mute")
        self.vol_icon.clicked.connect(self._engine.toggle_mute)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal, self._content_wrap)
        self.vol_slider.setObjectName("playerVolume")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self._engine.volume)
        self.vol_slider.setFixedWidth(130)
        self.vol_slider.valueChanged.connect(self._engine.set_volume)
        self.queue_btn = QPushButton("Queue", self._content_wrap)
        self.queue_btn.setObjectName("linkButton")
        self.queue_btn.clicked.connect(self._toggle_queue)
        self.lyrics_btn = QPushButton("Lyrics", self._content_wrap)
        self.lyrics_btn.setObjectName("linkButton")
        self.lyrics_btn.clicked.connect(self._toggle_lyrics)
        self.eq_btn = QPushButton("Equalizer", self._content_wrap)
        self.eq_btn.setObjectName("linkButton")
        self.eq_btn.clicked.connect(self._open_equalizer)
        self.open_lrc_btn = QPushButton("Open LRC", self._content_wrap)
        self.open_lrc_btn.setObjectName("linkButton")
        self.open_lrc_btn.clicked.connect(self._open_lrc_file)
        self.mini_btn = QPushButton("Mini Player", self._content_wrap)
        self.mini_btn.setObjectName("linkButton")
        self.mini_btn.clicked.connect(self._open_mini_player)
        bottom.addWidget(self.vol_icon)
        bottom.addWidget(self.vol_slider)
        bottom.addStretch(1)
        for button in (
            self.queue_btn,
            self.lyrics_btn,
            self.eq_btn,
            self.open_lrc_btn,
            self.mini_btn,
        ):
            bottom.addWidget(button)
        content.addLayout(bottom)

        # Lyrics section - directly below track info/controls
        self.lyrics_panel = QFrame(self._content_wrap)
        self.lyrics_panel.setObjectName("lyricsPanel")
        self.lyrics_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        lp = QVBoxLayout(self.lyrics_panel)
        lp.setContentsMargins(22, 20, 22, 20)
        lp.setSpacing(10)
        self.lyrics_title = QLabel("LYRICS", self.lyrics_panel)
        self.lyrics_title.setObjectName("sectionTitle")
        lp.addWidget(self.lyrics_title)
        self.lyrics_status = QLabel(
            "Lyrics aren't available for this track.", self.lyrics_panel
        )
        self.lyrics_status.setObjectName("pageSubtitle")
        self.lyrics_status.setWordWrap(True)
        self.lyrics_status.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        lp.addWidget(self.lyrics_status)
        self.lyrics_list = QListWidget(self.lyrics_panel)
        self.lyrics_list.setObjectName("lyricsList")
        self.lyrics_list.setSpacing(2)
        self.lyrics_list.setFrameShape(QFrame.Shape.NoFrame)
        self.lyrics_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.lyrics_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.lyrics_list.setMinimumHeight(140)
        self.lyrics_list.setMaximumHeight(420)
        self.lyrics_list.itemClicked.connect(self._seek_to_lyric)
        lp.addWidget(self.lyrics_list)
        content.addWidget(self.lyrics_panel)

        content.addStretch(1)
        root.addWidget(
            self._content_wrap,
            0,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
        )
        root.addStretch(1)
        self.body.addWidget(self.canvas, 1)

        self._engine.state_changed.connect(lambda _s: self._sync_controls())
        self._engine.track_changed.connect(self._on_track_changed)
        self._engine.position_changed.connect(self._on_position)
        self._engine.duration_changed.connect(self._on_duration)
        self._engine.queue_changed.connect(self._sync_controls)
        self._engine.volume_changed.connect(self._on_volume)
        self._engine.muted_changed.connect(lambda _m: self._sync_controls())
        self._engine.queue_manager.shuffle_changed.connect(
            lambda _v: self._sync_controls()
        )
        self._engine.queue_manager.repeat_changed.connect(
            lambda _v: self._sync_controls()
        )

        self.refresh_theme(theme_manager.colors)
        self._on_track_changed(self._engine.current_track)
        self._on_duration(self._engine.duration)
        self._on_position(self._engine.position)
        self._sync_controls()

    # ------------------------------------------------------------------ build

    def _btn(self, icon_name: str, tooltip: str) -> QPushButton:
        b = QPushButton(self)
        b.setObjectName("playerButton")
        b.setFixedSize(40, 40)
        b.setIconSize(QSize(19, 19))
        b.setToolTip(tooltip)
        b.setProperty("iconName", icon_name)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _toggle_queue(self) -> None:
        w = self.window()
        fn = getattr(w, "_toggle_queue_panel", None)
        if callable(fn):
            fn()

    def _open_equalizer(self) -> None:
        w = self.window()
        fn = getattr(w, "navigate", None)
        if callable(fn):
            fn("equalizer")

    def _toggle_lyrics(self) -> None:
        self.lyrics_panel.setVisible(not self.lyrics_panel.isVisible())

    def _open_mini_player(self) -> None:
        w = self.window()
        fn = getattr(w, "show_mini_player", None)
        if callable(fn):
            fn()

    def _open_lrc_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open lyrics file",
            str(Path.home()),
            "LRC files (*.lrc);;All files (*)",
        )
        if path:
            self._explicit_lrc = path
            self._load_lyrics()

    # ---------------------------------------------------------------- playback

    def _seek_released(self) -> None:
        self._seeking = False
        self._engine.set_position(self.progress.value())

    def _on_track_changed(self, track) -> None:
        self._explicit_lrc = None
        self._active_lyric_index = -1
        if track is None:
            self._current_path = None
            self.title_label.setText("No track playing")
            self.artist_label.setText("Select a song to start playback")
            self.album_label.setText("")
            self._set_artwork(None)
            self._clear_lyrics("No track playing.")
            self._sync_controls()
            return
        path = str(track.path)
        self._current_path = path
        title = track.title or Path(path).stem
        artist = track.artist or "Unknown artist"
        album = ""
        artwork = None
        if self._db is not None:
            try:
                rec = self._db.get_track_by_path(path)
                if rec:
                    title = rec.title or title
                    artist = rec.artist or artist
                    album = rec.album or ""
                    artwork = rec.artwork_path
            except Exception:
                pass
        try:
            queue_current = self._engine.queue_manager.current_item
            if queue_current is not None and str(queue_current.path) == path:
                # Fill missing fields only; DB/library metadata is preferred.
                if not title or title == Path(path).stem:
                    title = queue_current.title or title
                if not artist or artist == "Unknown artist":
                    artist = queue_current.artist or artist
                if not album:
                    album = queue_current.album or album
                if not artwork:
                    artwork = queue_current.artwork_path or artwork
        except Exception:
            pass
        self.title_label.setText(title)
        self.artist_label.setText(artist)
        self.album_label.setText(album)
        self._set_artwork(artwork)
        self._sync_favorite(path)
        # Deferred off the track-changed signal path: lyrics loading does disk
        # I/O (up to ~100ms on first hit) and must not delay the player bar /
        # MPRIS title update that follows this slot in the same emission.
        QTimer.singleShot(0, self._load_lyrics)
        self._sync_controls()

    def _on_duration(self, duration: int) -> None:
        self.progress.setRange(0, max(0, int(duration)))
        self.duration_time.setText(format_time(duration))
        self.progress.setEnabled(duration > 0)

    def _on_position(self, position: int) -> None:
        if not self._seeking:
            self.progress.blockSignals(True)
            self.progress.setValue(
                min(max(0, int(position)), self.progress.maximum())
            )
            self.progress.blockSignals(False)
            self.current_time.setText(format_time(position))
        self._sync_lyrics_active(position)

    def _on_volume(self, vol: int) -> None:
        self.vol_slider.blockSignals(True)
        self.vol_slider.setValue(int(vol))
        self.vol_slider.blockSignals(False)

    def _sync_controls(self) -> None:
        has_track = self._engine.current_track is not None
        playing = self._engine.playback_state == STATE_PLAYING
        self.play_btn.setEnabled(has_track)
        self.prev_btn.setEnabled(has_track)
        self.next_btn.setEnabled(
            self._engine.queue_manager.next_index(manual=True) is not None
        )
        self.shuffle_btn.setEnabled(True)
        self.repeat_btn.setEnabled(True)
        self.fav_btn.setEnabled(has_track)
        self.play_btn.setProperty("iconName", "pause" if playing else "play")
        self.play_btn.setToolTip("Pause" if playing else "Play")
        self.shuffle_btn.setProperty(
            "active", "true" if self._engine.queue_manager.shuffle else "false"
        )
        self.repeat_btn.setProperty(
            "active",
            "true" if self._engine.queue_manager.repeat_mode != "off" else "false",
        )
        repeat_mode = self._engine.queue_manager.repeat_mode
        self.repeat_btn.setProperty(
            "iconName", "repeat-one" if repeat_mode == "one" else "repeat"
        )
        self.repeat_btn.setToolTip(f"Repeat: {repeat_mode}")
        vol_icon = (
            "volume-muted"
            if self._engine.muted or self._engine.volume == 0
            else ("volume-low" if self._engine.volume < 45 else "volume")
        )
        self.vol_icon.setProperty("iconName", vol_icon)
        if has_track and self._current_path:
            self._sync_favorite(self._current_path)
        self._refresh_icons()
        for btn in (self.shuffle_btn, self.repeat_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _refresh_icons(self) -> None:
        for btn in self.findChildren(QPushButton):
            name = btn.property("iconName")
            if not name:
                continue
            color = (
                self._colors.accent
                if btn.property("active") == "true"
                else self._colors.text_muted
            )
            if btn is self.play_btn and btn.objectName() == "nowPlayingPlay":
                color = self._colors.accent_text
            btn.setIcon(icon(str(name), color, btn.iconSize().width()))

    def _toggle_favorite(self) -> None:
        if not self._current_path or self._db is None:
            return
        try:
            rec = self._db.get_track_by_path(self._current_path)
            if rec:
                self._db.toggle_favorite(rec.id)
                self._sync_favorite(self._current_path)
                page = (
                    getattr(self.window(), "pages", {}).get("favorites")
                    if self.window()
                    else None
                )
                if page and hasattr(page, "refresh_library"):
                    page.refresh_library()
        except Exception:
            pass

    def _sync_favorite(self, path: str) -> None:
        if self._db is None:
            return
        try:
            rec = self._db.get_track_by_path(path)
            fav = self._db.is_favorite(rec.id) if rec else False
            self.fav_btn.setProperty("iconName", "heart-filled" if fav else "favorites")
            self.fav_btn.setToolTip(
                "Remove from Favorites" if fav else "Add to Favorites"
            )
            self._refresh_icons()
        except Exception:
            pass

    # -------------------------------------------------------------------- lyrics

    def _clear_lyrics(self, msg: str) -> None:
        self._lyrics = None
        self._active_lyric_index = -1
        self.lyrics_list.clear()
        self.lyrics_status.setText(msg)
        self.lyrics_status.setVisible(True)
        self.lyrics_list.setVisible(False)

    def _load_lyrics(self) -> None:
        try:
            # May run from a deferred singleShot after the page was deleted
            # (rapid shutdown/teardown); the C++ widget would be gone.
            self.lyrics_list.count()
        except RuntimeError:
            return
        if not self._current_path:
            self._clear_lyrics("No track playing.")
            return
        try:
            data = self._lyrics_service.load_for_track(
                self._current_path, explicit_lrc=self._explicit_lrc
            )
        except Exception:
            data = None
        if not data or not data.lines:
            self._clear_lyrics("Lyrics aren't available for this track.")
            return
        self._lyrics = data
        self._active_lyric_index = -1
        self.lyrics_list.clear()
        synced = data.is_synced
        for line in data.lines:
            display = line.text if line.text.strip() else " "
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, line.time_ms)
            item.setData(Qt.ItemDataRole.UserRole + 1, bool(synced))
            # Blank lines should be subtle spacing, not giant items.
            if not line.text.strip():
                item.setSizeHint(QSize(0, 18))
            else:
                item.setSizeHint(QSize(0, 30))
            item.setForeground(
                QColor(self._colors.text if not synced else self._colors.text_muted)
            )
            font = item.font()
            font.setPointSizeF(11.0)
            item.setFont(font)
            self.lyrics_list.addItem(item)
        self.lyrics_status.setVisible(False)
        self.lyrics_list.setVisible(True)
        if synced:
            self._sync_lyrics_active(self._engine.position)
        else:
            # Unsynchronized: show as readable text, no fake active line.
            self.lyrics_list.setCurrentRow(-1)

    def _sync_lyrics_active(self, position_ms: int) -> None:
        if not self._lyrics or not self._lyrics.lines or not self._lyrics.is_synced:
            return
        idx = self._lyrics_service.active_line_index(self._lyrics.lines, position_ms)
        if idx == self._active_lyric_index:
            return
        previous = self._active_lyric_index
        self._active_lyric_index = idx
        for i in range(self.lyrics_list.count()):
            item = self.lyrics_list.item(i)
            if item is None:
                continue
            is_active = i == idx
            is_past = idx >= 0 and i < idx
            font = item.font()
            font.setBold(is_active)
            font.setPointSizeF(12.0 if is_active else 11.0)
            item.setFont(font)
            if is_active:
                item.setForeground(QColor(self._colors.accent))
            elif is_past:
                item.setForeground(QColor(self._colors.text_faint))
            else:
                item.setForeground(QColor(self._colors.text_muted))
        if idx >= 0 and idx < self.lyrics_list.count():
            self.lyrics_list.scrollToItem(
                self.lyrics_list.item(idx),
                QListWidget.ScrollHint.PositionAtCenter,
            )

    def _seek_to_lyric(self, item: QListWidgetItem) -> None:
        ms = item.data(Qt.ItemDataRole.UserRole)
        synced = bool(item.data(Qt.ItemDataRole.UserRole + 1))
        if synced and ms is not None and int(ms) >= 0:
            self._engine.set_position(int(ms))

    # ------------------------------------------------------------------ artwork

    def _set_artwork(self, artwork_path: str | None) -> None:
        self._current_artwork = artwork_path
        self._ambient.request(artwork_path)
        size = self.artwork.width() or ARTWORK_SIZE
        pixmap, key = request_rounded_pixmap(
            artwork_path,
            size,
            24,
            fallback_color=self._colors.surface_alt,
            fallback_icon="note",
        )
        self._art_key = key
        self.artwork.setText("")
        self.artwork.setStyleSheet(
            "QLabel#nowPlayingArtwork { background: transparent; border: none; }"
        )
        if pixmap is not None:
            self.artwork.setPixmap(pixmap)

    def _on_artwork_ready(self, key, pixmap) -> None:
        if key != self._art_key or pixmap is None:
            return
        try:
            self.artwork.setText("")
            self.artwork.setStyleSheet(
                "QLabel#nowPlayingArtwork { background: transparent; border: none; }"
            )
            self.artwork.setPixmap(pixmap)
        except Exception:
            pass

    def _on_ambient_ready(self, path: str, _palette: object) -> None:
        if path == (self._current_artwork or ""):
            self._apply_ambient()

    def _apply_ambient(self) -> None:
        # Global app background handles the blurred cover. Keep page transparent
        # to avoid double rendering work.
        self.clear_ambient_gradient()

    # ------------------------------------------------------------------- layout

    def _apply_responsive(self) -> None:
        width = self.viewport().width() if self.viewport() else self.width()
        art = ARTWORK_SMALL if width < 900 else ARTWORK_SIZE
        if self.artwork.width() != art:
            self.artwork.setFixedSize(art, art)
            self._set_artwork(self._current_artwork)
        self.lyrics_list.setMaximumHeight(360 if width < 900 else 420)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive()

    # -------------------------------------------------------------------- theme

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self._sync_controls()
        if self._lyrics:
            self._active_lyric_index = -1
            if self._lyrics.is_synced:
                self._sync_lyrics_active(self._engine.position)
            else:
                # Recolor unsynced lines
                for i in range(self.lyrics_list.count()):
                    item = self.lyrics_list.item(i)
                    if item is not None:
                        item.setForeground(QColor(self._colors.text))
        self._set_artwork(self._current_artwork)
        self._apply_ambient()
        self._apply_responsive()

    def refresh_library(self) -> None:
        self._on_track_changed(self._engine.current_track)
