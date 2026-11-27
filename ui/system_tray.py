"""System tray integration for ISAI."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from services.audio_engine import STATE_PLAYING
from ui.icons import icon as make_icon


class SystemTrayService(QObject):
    def __init__(self, theme_manager, audio_engine, parent=None):
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._engine = audio_engine
        self._tray = None
        self._menu = None
        self._play_action = None
        self._track_action = None
        self._show_cb = None
        self._quit_cb = None

    @property
    def available(self) -> bool:
        try:
            return QSystemTrayIcon.isSystemTrayAvailable()
        except Exception:
            return False

    def start(self, show_cb=None, quit_cb=None) -> bool:
        if self._tray is not None:
            return True
        if not self.available:
            return False
        self._show_cb = show_cb
        self._quit_cb = quit_cb
        try:
            tray = QSystemTrayIcon(self._icon(), self.parent())
            tray.setToolTip("ISAI")
            menu = QMenu()
            self._track_action = QAction("No track playing", menu)
            self._track_action.setEnabled(False)
            menu.addAction(self._track_action)
            menu.addSeparator()
            show_action = QAction("Show ISAI", menu)
            show_action.triggered.connect(self._show)
            menu.addAction(show_action)
            menu.addSeparator()
            self._play_action = QAction("Play", menu)
            self._play_action.triggered.connect(self._engine.toggle_play_pause)
            menu.addAction(self._play_action)
            prev_action = QAction("Previous", menu)
            prev_action.triggered.connect(self._engine.previous_track)
            menu.addAction(prev_action)
            next_action = QAction("Next", menu)
            next_action.triggered.connect(self._engine.next_track)
            menu.addAction(next_action)
            menu.addSeparator()
            quit_action = QAction("Quit ISAI", menu)
            quit_action.triggered.connect(self._quit)
            menu.addAction(quit_action)
            tray.setContextMenu(menu)
            tray.activated.connect(self._activated)
            tray.show()
            self._tray = tray
            self._menu = menu
            self._connect()
            self.refresh()
            return True
        except Exception:
            self._tray = None
            self._menu = None
            return False

    def _icon(self) -> QIcon:
        try:
            c = self._theme_manager.colors
            return make_icon("note", c.accent, 24)
        except Exception:
            return QIcon()

    def _connect(self):
        self._engine.state_changed.connect(lambda _s: self.refresh())
        self._engine.track_changed.connect(lambda _t: self.refresh())
        self._theme_manager.theme_changed.connect(lambda _t: self._refresh_icon())

    def _refresh_icon(self):
        if self._tray is not None:
            self._tray.setIcon(self._icon())

    def refresh(self):
        if self._tray is None:
            return
        playing = self._engine.playback_state == STATE_PLAYING
        if self._play_action is not None:
            self._play_action.setText("Pause" if playing else "Play")
        track = self._engine.current_track
        if self._track_action is not None:
            if track is None:
                self._track_action.setText("No track playing")
            else:
                txt = track.title
                if track.artist and track.artist != "Unknown artist":
                    txt = f"{track.title} — {track.artist}"
                self._track_action.setText(txt[:80])
        self._refresh_icon()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show()

    def _show(self):
        if callable(self._show_cb):
            try: self._show_cb()
            except Exception: pass

    def _quit(self):
        if callable(self._quit_cb):
            try: self._quit_cb()
            except Exception: pass

    def shutdown(self):
        try:
            if self._tray is not None:
                self._tray.hide()
                self._tray.deleteLater()
        except Exception:
            pass
        self._tray = None
        self._menu = None
