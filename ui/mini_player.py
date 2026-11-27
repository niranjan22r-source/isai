"""Compact always-on-top-friendly mini player window for ISAI."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import DARK, ThemeColors, ThemeManager
from services.ambient_palette import ambient_gradient_qss, ambient_service
from services.audio_engine import AudioEngine, STATE_PLAYING
from ui.components.artwork import artwork_ready_connect, request_rounded_pixmap
from ui.icons import icon
from ui.player_bar import format_time

ART_SIZE = 84


class MiniPlayerWindow(QWidget):
    def __init__(
        self,
        theme_manager: ThemeManager,
        audio_engine: AudioEngine,
        library_db,
        on_restore=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("ISAI Mini Player")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("miniPlayer")
        self.resize(460, 172)
        self.setMinimumSize(380, 150)

        self._theme_manager = theme_manager
        self._engine = audio_engine
        self._db = library_db
        self._on_restore = on_restore
        self._colors = theme_manager.colors
        self._seeking = False
        self._closing = False
        self._artwork_path: str | None = None
        self._art_key = None
        self._ambient = ambient_service()
        self._ambient.palette_ready.connect(self._on_ambient_ready)
        artwork_ready_connect(self._on_artwork_ready)

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(16)

        self.art = QLabel(self)
        self.art.setObjectName("playerArtwork")
        self.art.setFixedSize(ART_SIZE, ART_SIZE)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.art, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(4)
        self.eyebrow = QLabel("NOW PLAYING", self)
        self.eyebrow.setObjectName("sectionHint")
        col.addWidget(self.eyebrow)
        self.title = QLabel("No track playing", self)
        self.title.setObjectName("miniTitle")
        self.title.setWordWrap(False)
        self.artist = QLabel("", self)
        self.artist.setObjectName("miniArtist")
        self.artist.setWordWrap(False)
        col.addWidget(self.title)
        col.addWidget(self.artist)

        prog = QHBoxLayout()
        prog.setContentsMargins(0, 4, 0, 0)
        prog.setSpacing(8)
        self.pos_label = QLabel("0:00", self)
        self.pos_label.setObjectName("playerTime")
        self.pos_label.setFixedWidth(40)
        self.progress = QSlider(Qt.Orientation.Horizontal, self)
        self.progress.setObjectName("playerProgress")
        self.progress.setRange(0, 0)
        self.progress.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.progress.sliderReleased.connect(self._seek_released)
        self.progress.sliderMoved.connect(lambda v: self.pos_label.setText(format_time(v)))
        self.dur_label = QLabel("0:00", self)
        self.dur_label.setObjectName("playerTime")
        self.dur_label.setFixedWidth(40)
        prog.addWidget(self.pos_label)
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.dur_label)
        col.addLayout(prog)

        ctrls = QHBoxLayout()
        ctrls.setContentsMargins(0, 4, 0, 0)
        ctrls.setSpacing(6)
        self.prev_btn = self._btn("previous", "Previous")
        self.prev_btn.clicked.connect(self._engine.previous_track)
        self.play_btn = self._btn("play", "Play")
        self.play_btn.setObjectName("playButton")
        self.play_btn.setFixedSize(44, 44)
        self.play_btn.setIconSize(QSize(20, 20))
        self.play_btn.clicked.connect(self._engine.toggle_play_pause)
        self.next_btn = self._btn("next", "Next")
        self.next_btn.clicked.connect(self._engine.next_track)
        self.restore_btn = QPushButton("Main Window", self)
        self.restore_btn.setObjectName("secondaryButton")
        self.restore_btn.clicked.connect(self._restore)
        ctrls.addWidget(self.prev_btn)
        ctrls.addWidget(self.play_btn)
        ctrls.addWidget(self.next_btn)
        ctrls.addStretch(1)
        ctrls.addWidget(self.restore_btn)
        col.addLayout(ctrls)

        root.addLayout(col, 1)

        self._engine.track_changed.connect(self._on_track_changed)
        self._engine.state_changed.connect(lambda _s: self._sync())
        self._engine.position_changed.connect(self._on_position)
        self._engine.duration_changed.connect(self._on_duration)
        self._engine.queue_changed.connect(self._sync)

        self.refresh_theme(theme_manager.colors)
        self._on_track_changed(self._engine.current_track)
        self._on_duration(self._engine.duration)
        self._on_position(self._engine.position)
        self._sync()

    def _btn(self, name: str, tooltip: str) -> QPushButton:
        b = QPushButton(self)
        b.setObjectName("playerButton")
        b.setFixedSize(32, 32)
        b.setIconSize(QSize(18, 18))
        b.setToolTip(tooltip)
        b.setProperty("iconName", name)
        return b

    def _restore(self) -> None:
        if callable(self._on_restore):
            self._on_restore()
        self.close()

    def _seek_released(self) -> None:
        self._seeking = False
        self._engine.set_position(self.progress.value())

    def _on_track_changed(self, track) -> None:
        self._artwork_path = None
        if track is None:
            self.title.setText("No track playing")
            self.artist.setText("")
        else:
            title = track.title or Path(track.path).stem
            artist = track.artist or "Unknown artist"
            self.title.setText(title)
            self.artist.setText(artist)
            self.title.setToolTip(title)
            self.artist.setToolTip(artist)
            try:
                cur = self._engine.queue_manager.current_item
                if cur is not None and Path(cur.path).resolve() == Path(track.path).resolve():
                    self._artwork_path = cur.artwork_path
            except Exception:
                pass
            if self._artwork_path is None:
                try:
                    rec = self._db.get_track_by_path(str(track.path))
                    self._artwork_path = rec.artwork_path if rec else None
                except Exception:
                    self._artwork_path = None
        self._update_art()
        self._apply_ambient()
        self._sync()

    def _update_art(self) -> None:
        pixmap, key = request_rounded_pixmap(
            self._artwork_path,
            ART_SIZE,
            16,
            fallback_color=self._colors.surface_alt,
            fallback_icon="note",
        )
        self._art_key = key
        if pixmap is not None:
            self.art.setPixmap(pixmap)
            self.art.setText("")

    def _on_artwork_ready(self, key, pixmap) -> None:
        if key != self._art_key or pixmap is None:
            return
        try:
            self.art.setPixmap(pixmap)
            self.art.setText("")
        except Exception:
            pass

    def _apply_ambient(self) -> None:
        palette = self._ambient.cached(self._artwork_path)
        if palette is None and self._artwork_path:
            self._ambient.request(self._artwork_path)
        gradient = ambient_gradient_qss(
            palette,
            dark=self._theme_manager.effective_theme == DARK,
            base=self._colors.bg,
            fallback_glow=self._colors.ambient,
        )
        self.setStyleSheet(
            "QWidget#miniPlayer { background: %s; border: 1px solid %s; "
            "border-radius: 20px; color: %s; }"
            % (gradient, self._colors.border_strong, self._colors.text)
        )

    def _on_ambient_ready(self, path: str, _palette: object) -> None:
        if path == self._artwork_path:
            self._apply_ambient()

    def _on_duration(self, d: int) -> None:
        self.progress.setRange(0, max(0, int(d)))
        self.dur_label.setText(format_time(d))
        self.progress.setEnabled(d > 0)

    def _on_position(self, p: int) -> None:
        if not self._seeking:
            self.progress.blockSignals(True)
            self.progress.setValue(min(max(0, int(p)), self.progress.maximum()))
            self.progress.blockSignals(False)
            self.pos_label.setText(format_time(p))

    def _sync(self) -> None:
        has = self._engine.current_track is not None
        playing = self._engine.playback_state == STATE_PLAYING
        self.play_btn.setEnabled(has)
        self.prev_btn.setEnabled(has)
        self.next_btn.setEnabled(
            self._engine.queue_manager.next_index(manual=True) is not None
        )
        self.play_btn.setIcon(
            icon(
                "pause" if playing else "play",
                self._colors.accent_text if has else self._colors.text_faint,
                19,
            )
        )
        self.prev_btn.setIcon(
            icon("previous", self._colors.text if has else self._colors.text_faint, 18)
        )
        self.next_btn.setIcon(
            icon(
                "next",
                self._colors.text
                if self.next_btn.isEnabled()
                else self._colors.text_faint,
                18,
            )
        )

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self._apply_ambient()
        self._update_art()
        self._sync()

    def closeEvent(self, event):  # noqa: N802
        if not self._closing:
            self._closing = True
            try:
                if callable(self._on_restore):
                    self._on_restore()
            except Exception:
                pass
        super().closeEvent(event)
