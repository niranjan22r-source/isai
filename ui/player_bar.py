"""Persistent bottom player bar backed by the real audio engine."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from services.audio_engine import AudioEngine, STATE_PLAYING, TrackInfo
from services.queue_manager import REPEAT_ALL, REPEAT_OFF, REPEAT_ONE
from ui.components.artwork import artwork_ready_connect, request_rounded_pixmap
from ui.icons import icon

NO_TRACK_TITLE = "No track playing"
NO_TRACK_HINT = "Open an audio file to begin."
NO_TRACK_TOOLTIP = "Use File → Open Audio Files… (Ctrl+O)"
SEEK_HINT = "Drag to seek"
ERROR_DISPLAY_MS = 6000


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def format_time(milliseconds: int) -> str:
    """Format milliseconds as m:ss, or h:mm:ss for long tracks."""
    total_seconds = max(0, int(milliseconds) // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class PlayerBar(QWidget):
    """Bottom playback bar: track info, transport, seek, volume, queue."""

    queue_toggled = Signal(bool)
    track_info_clicked = Signal()
    eq_requested = Signal()

    def __init__(
        self,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
        audio_engine: AudioEngine | None = None,
        library_db=None,
        engine: AudioEngine | None = None,
    ) -> None:
        # Compatibility: allow old call styles.
        if isinstance(parent, AudioEngine):
            audio_engine = parent
            parent = None
        audio_engine = audio_engine or engine
        super().__init__(parent)
        self.setObjectName("playerBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(88)

        self._theme_manager = theme_manager
        self._engine = audio_engine
        self._library_db = library_db
        self._colors = theme_manager.colors
        self._track: TrackInfo | None = None
        self._duration = 0
        self._seeking = False
        self._current_track_id: int | None = None
        self._is_favorite = False
        self._queue_visible = False
        self.on_favorite_changed = None  # callback(track_id, is_favorite)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(ERROR_DISPLAY_MS)
        self._status_timer.timeout.connect(self._restore_track_text)

        self._art_key = None
        artwork_ready_connect(self._on_artwork_ready)

        self._build_ui()
        self.refresh_theme(self._colors)
        self._connect_engine()
        self._sync_from_engine()

    # --------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)

        layout.addWidget(self._build_track_info(), stretch=3)
        layout.addWidget(self._build_center(), stretch=5)
        layout.addWidget(self._build_right(), stretch=3)

    def _build_track_info(self) -> QWidget:
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self.artwork_label = QLabel(container)
        self.artwork_label.setObjectName("playerArtwork")
        self.artwork_label.setFixedSize(64, 64)
        self.artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artwork_label.mousePressEvent = lambda e: self.track_info_clicked.emit()

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addStretch(1)

        self.track_title = QLabel(NO_TRACK_TITLE, container)
        self.track_title.setObjectName("playerTrackTitle")
        self.track_title.setProperty("inactive", "true")
        self.track_title.setWordWrap(False)
        self.track_title.setMinimumWidth(120)
        self.track_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.track_title.mousePressEvent = lambda e: self.track_info_clicked.emit()

        self.track_artist = QLabel(NO_TRACK_HINT, container)
        self.track_artist.setObjectName("playerTrackArtist")
        self.track_artist.setWordWrap(False)
        self.track_artist.setMinimumWidth(120)

        text_col.addWidget(self.track_title)
        text_col.addWidget(self.track_artist)
        text_col.addStretch(1)

        self.favorite_button = self._make_button(
            "favorites", "Add to favorites", icon_size=18, accessible_name="Favorite"
        )
        self.favorite_button.clicked.connect(self._toggle_favorite)

        row.addWidget(self.artwork_label)
        row.addLayout(text_col, stretch=1)
        row.addWidget(self.favorite_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        return container

    def _build_center(self) -> QWidget:
        container = QWidget(self)
        col = QVBoxLayout(container)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addStretch(1)

        self.shuffle_button = self._make_button("shuffle", "Shuffle: off", icon_size=18, accessible_name="Shuffle")
        self.shuffle_button.clicked.connect(self._toggle_shuffle)
        self.previous_button = self._make_button("previous", "Previous track", icon_size=18, accessible_name="Previous")
        self.play_button = self._make_button("play", "Play", icon_size=20, accessible_name="Play")
        self.play_button.setObjectName("playButton")
        self.play_button.setFixedSize(44, 44)
        self.next_button = self._make_button("next", "Next track", icon_size=18, accessible_name="Next")
        self.repeat_button = self._make_button("repeat", "Repeat: off", icon_size=18, accessible_name="Repeat")
        self.repeat_button.clicked.connect(self._cycle_repeat)

        controls.addWidget(self.shuffle_button)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.repeat_button)
        controls.addStretch(1)

        # The seek row is a real widget so the whole row can disappear while
        # the immersive Now Playing page owns the seek interaction.
        self.progress_row = QWidget(container)
        self.progress_row.setObjectName("playerProgressRow")
        progress_row = QHBoxLayout(self.progress_row)
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(8)

        self.current_time = QLabel("0:00", self.progress_row)
        self.current_time.setObjectName("playerTime")
        self.current_time.setFixedWidth(46)
        self.current_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.progress_slider = QSlider(Qt.Orientation.Horizontal, self.progress_row)
        self.progress_slider.setObjectName("playerProgress")
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setEnabled(False)
        self.progress_slider.setToolTip(NO_TRACK_HINT)

        self.duration_time = QLabel("0:00", self.progress_row)
        self.duration_time.setObjectName("playerTime")
        self.duration_time.setFixedWidth(46)
        self.duration_time.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        progress_row.addWidget(self.current_time)
        progress_row.addWidget(self.progress_slider, stretch=1)
        progress_row.addWidget(self.duration_time)

        col.addLayout(controls)
        col.addWidget(self.progress_row)
        return container

    def _build_right(self) -> QWidget:
        container = QWidget(self)
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addStretch(1)

        self.eq_button = self._make_button("equalizer", "Equalizer", icon_size=18, accessible_name="Equalizer")
        self.eq_button.setEnabled(True)
        self.eq_button.clicked.connect(self.eq_requested.emit)

        self.queue_button = self._make_button("queue", "Show queue (Ctrl+Q)", icon_size=18, accessible_name="Queue")
        self.queue_button.setEnabled(True)
        self.queue_button.clicked.connect(self._toggle_queue_panel)

        self.volume_button = self._make_button("volume", "Mute", icon_size=18, accessible_name="Mute")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, container)
        self.volume_slider.setObjectName("playerVolume")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setEnabled(False)

        row.addWidget(self.eq_button)
        row.addWidget(self.queue_button)
        row.addSpacing(4)
        row.addWidget(self.volume_button)
        row.addWidget(self.volume_slider)
        return container

    def _make_button(self, icon_name: str, tooltip: str, icon_size: int = 18, accessible_name: str = "") -> QPushButton:
        button = QPushButton(self)
        button.setObjectName("playerButton")
        button.setFixedSize(32, 32)
        button.setIconSize(QSize(icon_size, icon_size))
        button.setEnabled(False)
        button.setToolTip(tooltip)
        button.setProperty("iconName", icon_name)
        if accessible_name:
            button.setAccessibleName(accessible_name)
        return button

    # ----------------------------------------------------------------- wiring

    def _connect_engine(self) -> None:
        engine = self._engine
        if engine is None:
            return
        engine.state_changed.connect(self._on_state_changed)
        engine.position_changed.connect(self._on_position_changed)
        engine.duration_changed.connect(self._on_duration_changed)
        engine.track_changed.connect(self._on_track_changed)
        engine.queue_changed.connect(self._on_queue_changed)
        engine.volume_changed.connect(self._on_volume_changed)
        engine.muted_changed.connect(self._on_muted_changed)
        engine.error_occurred.connect(self.show_error)

        self.previous_button.clicked.connect(engine.previous_track)
        self.play_button.clicked.connect(engine.toggle_play_pause)
        self.next_button.clicked.connect(engine.next_track)
        self.volume_button.clicked.connect(engine.toggle_mute)
        self.volume_slider.valueChanged.connect(self._on_volume_slider_changed)
        self.progress_slider.sliderPressed.connect(self._on_seek_started)
        self.progress_slider.sliderMoved.connect(self._on_seek_preview)
        self.progress_slider.sliderReleased.connect(self._on_seek_finished)

        qm = engine.queue_manager
        qm.shuffle_changed.connect(lambda _v: self._update_controls())
        qm.repeat_changed.connect(lambda _v: self._update_controls())

    def _sync_from_engine(self) -> None:
        engine = self._engine
        if engine is None:
            self._apply_no_track()
            self._update_controls()
            return
        self._on_volume_changed(engine.volume)
        self._on_muted_changed(engine.muted)
        self._on_track_changed(engine.current_track)
        self._on_duration_changed(engine.duration)
        self._on_position_changed(engine.position)
        self._update_controls()

    # --------------------------------------------------------------- playback

    def _on_state_changed(self, _state: str) -> None:
        self._update_controls()

    def _on_track_changed(self, track: TrackInfo | None) -> None:
        self._status_timer.stop()
        self.track_artist.setProperty("error", "false")
        _repolish(self.track_artist)
        if track is None:
            self._apply_no_track()
            self._current_track_id = None
            self._is_favorite = False
        else:
            self._track = track
            self.track_title.setProperty("inactive", "false")
            _repolish(self.track_title)
            self._set_track_text(track.title, track.artist)
            self._sync_favorite_for_current_track()
        self._refresh_artwork()
        self._update_controls()

    def _on_queue_changed(self) -> None:
        self._update_controls()

    def _on_duration_changed(self, duration: int) -> None:
        self._duration = max(0, int(duration))
        self.progress_slider.blockSignals(True)
        self.progress_slider.setRange(0, self._duration)
        self.progress_slider.blockSignals(False)
        self.duration_time.setText(format_time(self._duration))
        self._update_controls()

    def _on_position_changed(self, position: int) -> None:
        if self._seeking:
            return
        self.progress_slider.blockSignals(True)
        self.progress_slider.setValue(min(max(0, int(position)), self.progress_slider.maximum()))
        self.progress_slider.blockSignals(False)
        self.current_time.setText(format_time(position))

    def _on_seek_started(self) -> None:
        self._seeking = True

    def _on_seek_preview(self, position: int) -> None:
        self.current_time.setText(format_time(position))

    def _on_seek_finished(self) -> None:
        self._seeking = False
        if self._engine is not None:
            self._engine.set_position(self.progress_slider.value())

    def _on_volume_slider_changed(self, value: int) -> None:
        if self._engine is not None:
            self._engine.set_volume(value)

    def _on_volume_changed(self, value: int) -> None:
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(value)
        self.volume_slider.blockSignals(False)
        self.volume_slider.setToolTip(f"Volume {value}%")

    def _on_muted_changed(self, muted: bool) -> None:
        self.volume_button.setToolTip("Unmute (Ctrl+M)" if muted else "Mute (Ctrl+M)")
        self.volume_button.setAccessibleName("Unmute" if muted else "Mute")
        self._refresh_icons()

    # --------------------------------------------------------------- controls

    def _toggle_shuffle(self) -> None:
        if self._engine is None:
            return
        self._engine.queue_manager.toggle_shuffle()
        self._update_controls()

    def _cycle_repeat(self) -> None:
        if self._engine is None:
            return
        self._engine.queue_manager.cycle_repeat_mode()
        self._update_controls()

    def _toggle_queue_panel(self) -> None:
        self._queue_visible = not self._queue_visible
        self.queue_toggled.emit(self._queue_visible)
        self._update_controls()

    def set_queue_visible(self, visible: bool) -> None:
        self._queue_visible = bool(visible)
        self._update_controls()

    def set_seek_visible(self, visible: bool) -> None:
        """Show the bottom seek row, or yield it to the Now Playing page."""
        self.progress_row.setVisible(bool(visible))

    # ----------------------------------------------------------------- state

    def set_library_db(self, library_db) -> None:
        self._library_db = library_db
        self._sync_favorite_for_current_track()
        self._update_controls()

    def _apply_no_track(self) -> None:
        self._track = None
        self.track_title.setProperty("inactive", "true")
        _repolish(self.track_title)
        self._set_track_text(NO_TRACK_TITLE, NO_TRACK_HINT)
        self.track_artist.setToolTip(NO_TRACK_TOOLTIP)
        self.current_time.setText("0:00")
        self.duration_time.setText("0:00")
        self.progress_slider.blockSignals(True)
        self.progress_slider.setRange(0, 0)
        self.progress_slider.setValue(0)
        self.progress_slider.blockSignals(False)
        self._duration = 0

    def _set_track_text(self, title: str, artist: str) -> None:
        self.track_title.setText(title)
        self.track_title.setToolTip(title)
        self.track_artist.setText(artist)
        self.track_artist.setToolTip(artist)

    def _restore_track_text(self) -> None:
        self.track_artist.setProperty("error", "false")
        _repolish(self.track_artist)
        if self._track is None:
            self._set_track_text(NO_TRACK_TITLE, NO_TRACK_HINT)
            self.track_artist.setToolTip(NO_TRACK_TOOLTIP)
        else:
            self._set_track_text(self._track.title, self._track.artist)

    def show_error(self, message: str) -> None:
        self.track_artist.setProperty("error", "true")
        _repolish(self.track_artist)
        self.track_artist.setText(message)
        self.track_artist.setToolTip(message)
        self._status_timer.start(ERROR_DISPLAY_MS)

    def _refresh_artwork(self) -> None:
        artwork_path = None
        # Prefer queue metadata to avoid DB work during rapid track changes.
        try:
            cur = self._engine.queue_manager.current_item if self._engine else None
            if cur is not None and getattr(cur, "artwork_path", None):
                artwork_path = cur.artwork_path
        except Exception:
            artwork_path = None
        if artwork_path is None and self._library_db is not None and self._track is not None:
            try:
                rec = self._library_db.get_track_by_path(str(self._track.path))
                artwork_path = rec.artwork_path if rec is not None else None
            except Exception:
                artwork_path = None
        pixmap, key = request_rounded_pixmap(
            artwork_path,
            60,
            12,
            fallback_color=self._colors.surface_alt,
            fallback_icon="note",
        )
        self._art_key = key
        if pixmap is not None:
            self.artwork_label.setPixmap(pixmap)

    def _on_artwork_ready(self, key, pixmap) -> None:
        if key != self._art_key or pixmap is None:
            return
        try:
            self.artwork_label.setPixmap(pixmap)
        except Exception:
            pass

    def _sync_favorite_for_current_track(self) -> None:
        self._current_track_id = None
        self._is_favorite = False
        if self._library_db is None or self._track is None:
            return
        try:
            rec = self._library_db.get_track_by_path(str(self._track.path))
            if rec is not None:
                self._current_track_id = rec.id
                self._is_favorite = self._library_db.is_favorite(rec.id)
        except Exception:
            self._current_track_id = None
            self._is_favorite = False

    def refresh_favorite_state(self) -> None:
        self._sync_favorite_for_current_track()
        self._update_controls()

    def _toggle_favorite(self) -> None:
        if self._library_db is None or self._current_track_id is None:
            return
        try:
            self._is_favorite = self._library_db.toggle_favorite(self._current_track_id)
        except Exception:
            return
        self._update_controls()
        callback = getattr(self, "on_favorite_changed", None)
        if callable(callback):
            callback(self._current_track_id, self._is_favorite)

    def _update_controls(self) -> None:
        engine = self._engine
        qm = engine.queue_manager if engine is not None else None
        has_engine = engine is not None
        has_track = has_engine and engine.current_track is not None
        has_queue = qm.has_tracks() if qm is not None else False
        playing = has_engine and engine.playback_state == STATE_PLAYING
        shuffle = qm.shuffle if qm is not None else False
        repeat = qm.repeat_mode if qm is not None else REPEAT_OFF

        can_go_next = False
        if qm is not None and has_queue:
            can_go_next = qm.next_index(manual=True) is not None
        can_go_prev = has_queue

        self.play_button.setEnabled(has_track)
        self.previous_button.setEnabled(can_go_prev or has_track)
        self.next_button.setEnabled(can_go_next)
        self.progress_slider.setEnabled(has_track and self._duration > 0)
        self.volume_slider.setEnabled(has_engine)
        self.volume_button.setEnabled(has_engine)
        self.shuffle_button.setEnabled(has_engine)
        self.repeat_button.setEnabled(has_engine)
        self.queue_button.setEnabled(True)

        self.favorite_button.setEnabled(has_track and self._library_db is not None and self._current_track_id is not None)
        self.favorite_button.setToolTip("Remove from favorites" if self._is_favorite else "Add to favorites")

        self.shuffle_button.setToolTip(f"Shuffle: {'on' if shuffle else 'off'} (Ctrl+S)")
        repeat_label = {"off": "off", "all": "all tracks", "one": "current track"}.get(repeat, repeat)
        self.repeat_button.setToolTip(f"Repeat: {repeat_label} (Ctrl+R)")

        if has_track:
            self.play_button.setToolTip("Pause (Space)" if playing else "Play (Space)")
            self.play_button.setAccessibleName("Pause" if playing else "Play")
            self.previous_button.setToolTip("Previous track (Ctrl+Left)")
            self.next_button.setToolTip("Next track (Ctrl+Right)" if can_go_next else "End of queue")
            self.progress_slider.setToolTip(SEEK_HINT)
        else:
            self.play_button.setToolTip(NO_TRACK_HINT)
            self.play_button.setAccessibleName("Play")
            self.previous_button.setToolTip(NO_TRACK_HINT)
            self.next_button.setToolTip(NO_TRACK_HINT)
            self.progress_slider.setToolTip(NO_TRACK_HINT)

        self.queue_button.setToolTip("Hide queue (Ctrl+Q)" if self._queue_visible else "Show queue (Ctrl+Q)")
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        colors = self._colors
        engine = self._engine
        qm = engine.queue_manager if engine is not None else None
        playing = engine is not None and engine.playback_state == STATE_PLAYING
        shuffle = qm.shuffle if qm is not None else False
        repeat = qm.repeat_mode if qm is not None else REPEAT_OFF
        muted = engine is not None and engine.muted

        self._refresh_artwork()

        def c(enabled: bool, active: bool = False):
            if active:
                return colors.accent
            return colors.text if enabled else colors.text_faint

        self.shuffle_button.setIcon(icon("shuffle", c(self.shuffle_button.isEnabled(), shuffle), 18))
        self.previous_button.setIcon(icon("previous", c(self.previous_button.isEnabled()), 18))
        self.next_button.setIcon(icon("next", c(self.next_button.isEnabled()), 18))
        play_color = colors.accent_text if self.play_button.isEnabled() else colors.text_faint
        self.play_button.setIcon(icon("pause" if playing else "play", play_color, 20))
        repeat_icon = "repeat-one" if repeat == REPEAT_ONE else "repeat"
        self.repeat_button.setIcon(icon(repeat_icon, c(self.repeat_button.isEnabled(), repeat != REPEAT_OFF), 18))

        fav_enabled = self.favorite_button.isEnabled()
        fav_color = colors.accent if (fav_enabled and self._is_favorite) else (colors.text_muted if fav_enabled else colors.text_faint)
        self.favorite_button.setIcon(icon("favorites", fav_color, 18))

        queue_color = colors.accent if self._queue_visible else colors.text
        self.queue_button.setIcon(icon("queue", queue_color, 18))
        self.volume_button.setIcon(icon("volume-muted" if muted else "volume", c(self.volume_button.isEnabled()), 18))

    # ------------------------------------------------------------------ theme

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self._refresh_icons()
