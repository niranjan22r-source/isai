"""Main window assembly: sidebar, page stack, player bar, and library import."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, QStandardPaths, QThread, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.app_settings import (
    AMBIENT_ARTWORK_KEY,
    ARTWORK_CACHE_LIMIT_MB_KEY,
    CLOSE_TO_TRAY_KEY,
    DEFAULT_REPEAT_KEY,
    DEFAULT_SHUFFLE_KEY,
    PLAYBACK_NOTIFICATIONS_KEY,
    REMEMBER_STATE_KEY,
    RESUME_POSITION_KEY,
    SCAN_ON_STARTUP_KEY,
    VOLUME_KEY,
    get_setting,
    set_setting,
)
from core.theme_manager import ThemeColors, ThemeManager
from services.artwork_cache import ArtworkCache
from services.audio_engine import AUDIO_FILE_FILTER, AudioEngine
from services.equalizer import EqualizerService
from services.library_database import LibraryDatabase
from services.mpris_service import MprisService
from services.music_scanner import MusicScannerWorker
from services.notification_service import NotificationService
from ui.pages import (
    AlbumsPage,
    ArtistsPage,
    EqualizerPage,
    FavoritesPage,
    HomePage,
    NowPlayingPage,
    PlaylistsPage,
    RecentlyPlayedPage,
    SettingsPage,
    SongsPage,
)
from ui.components.artwork import blurred_artwork_pixmap
from ui.components.queue_panel import QueuePanel
from ui.mini_player import MiniPlayerWindow
from ui.player_bar import PlayerBar
from ui.sidebar import Sidebar
from ui.system_tray import SystemTrayService

APP_NAME = "ISAI"
WINDOW_TITLE = "ISAI Music Player"
DEFAULT_WINDOW_WIDTH = 1200
DEFAULT_WINDOW_HEIGHT = 760
MINIMUM_WINDOW_WIDTH = 850
MINIMUM_WINDOW_HEIGHT = 550
SIDEBAR_AUTO_COLLAPSE_WIDTH = 1000


class MainWindow(QMainWindow):
    """ISAI's primary window."""

    def __init__(
        self,
        theme_manager: ThemeManager | None = None,
        parent: QWidget | None = None,
        library_db: LibraryDatabase | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)
        self.setMinimumSize(MINIMUM_WINDOW_WIDTH, MINIMUM_WINDOW_HEIGHT)

        self._theme_manager = (
            theme_manager if theme_manager is not None else ThemeManager(parent=self)
        )
        self._current_page_key = ""
        self._auto_collapsed = False
        self._scan_thread: QThread | None = None
        self._scan_worker: MusicScannerWorker | None = None
        self._mini_player: MiniPlayerWindow | None = None
        self._quitting = False

        self.library_db = library_db if library_db is not None else LibraryDatabase()
        # Settings (QSettings, shared via ThemeManager)
        settings = self._theme_manager._settings
        self.equalizer_service = EqualizerService(settings, self)
        self.audio_engine = AudioEngine(self, eq_service=self.equalizer_service)
        self.audio_engine.track_changed.connect(self._on_track_played)
        self.audio_engine.track_changed.connect(self._update_content_background)
        self.audio_engine.volume_changed.connect(self._on_volume_changed_save)
        self._notifications_enabled = bool(get_setting(settings, PLAYBACK_NOTIFICATIONS_KEY, True))
        self._close_to_tray = bool(get_setting(settings, CLOSE_TO_TRAY_KEY, True))
        self._scan_on_startup = bool(get_setting(settings, SCAN_ON_STARTUP_KEY, False))
        self._resume_position = bool(get_setting(settings, RESUME_POSITION_KEY, True))
        self._remember_state = bool(get_setting(settings, REMEMBER_STATE_KEY, True))

        self.notification_service = NotificationService(self)
        self.notification_service.set_enabled(self._notifications_enabled)
        self.mpris_service = MprisService(self.audio_engine, self.library_db, self)
        self.tray_service = SystemTrayService(self._theme_manager, self.audio_engine, self)

        # Apply playback defaults before restoring queue.
        try:
            self.audio_engine.set_volume(int(get_setting(settings, VOLUME_KEY, 70)))
        except Exception:
            pass

        self._queue_save_timer = QTimer(self)
        self._queue_save_timer.setSingleShot(True)
        self._queue_save_timer.setInterval(800)
        self._queue_save_timer.timeout.connect(self._save_queue_state)

        self._bg_update_timer = QTimer(self)
        self._bg_update_timer.setSingleShot(True)
        self._bg_update_timer.setInterval(120)
        self._bg_update_timer.timeout.connect(self._update_content_background)
        self.audio_engine.queue_changed.connect(self._schedule_queue_save)
        self.audio_engine.queue_manager.shuffle_changed.connect(lambda _v: self._schedule_queue_save())
        self.audio_engine.queue_manager.repeat_changed.connect(lambda _v: self._schedule_queue_save())
        self.audio_engine.position_changed.connect(self._on_position_for_save)

        self._theme_manager.apply(QApplication.instance())
        self._build_ui()
        self._build_menu()
        self._setup_shortcuts()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)
        self._refresh_theme()
        self.navigate("home")
        QTimer.singleShot(0, self._initial_load)

    def _initial_load(self) -> None:
        try:
            self.refresh_library_views()
        except Exception:
            pass
        try:
            self._restore_queue_state()
        except Exception:
            pass
        try:
            self.audio_engine.track_changed.connect(self._on_track_changed_notify)
        except Exception:
            pass
        try:
            self._start_desktop_integration()
        except Exception:
            pass
        if getattr(self, "_scan_on_startup", False):
            QTimer.singleShot(800, self._scan_registered_folders_if_enabled)

    @property
    def theme_manager(self) -> ThemeManager:
        return self._theme_manager

    @property
    def current_page_key(self) -> str:
        return self._current_page_key

    @property
    def current_page(self) -> QWidget | None:
        return self.page_stack.currentWidget()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("appRoot")
        self._bg_host = root
        self._content_bg = QLabel(root)
        self._content_bg.setObjectName("contentBackground")
        self._content_bg.setScaledContents(True)
        self._content_bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._content_overlay = QLabel(root)
        self._content_overlay.setObjectName("contentBackgroundOverlay")
        self._content_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        body = QWidget(root)
        body.setObjectName("bodyArea")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar(self._theme_manager, body)
        body_layout.addWidget(self.sidebar)

        content = QWidget(body)
        content.setObjectName("contentArea")
        self._content_area = content
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.page_stack = QStackedWidget(content)
        self.page_stack.setObjectName("pageStack")
        content_layout.addWidget(self.page_stack)
        self._content_bg.lower()
        self._content_overlay.lower()

        self.pages: dict[str, QWidget] = {
            "home": HomePage(self._theme_manager, self.navigate, self.library_db, self.audio_engine, self.page_stack),
            "now_playing": NowPlayingPage(self._theme_manager, self.library_db, self.audio_engine, self.page_stack),
            "songs": SongsPage(self._theme_manager, self.library_db, self.audio_engine, self.page_stack),
            "albums": AlbumsPage(self._theme_manager, self.library_db, self.audio_engine, self.page_stack),
            "artists": ArtistsPage(self._theme_manager, self.library_db, self.audio_engine, self.navigate, self.page_stack),
            "playlists": PlaylistsPage(self._theme_manager, self.library_db, self.audio_engine, self.page_stack),
            "favorites": FavoritesPage(self._theme_manager, self.library_db, self.audio_engine, self.page_stack),
            "recent": RecentlyPlayedPage(self._theme_manager, self.library_db, self.audio_engine, self.page_stack),
            "equalizer": EqualizerPage(self._theme_manager, self.equalizer_service, self.page_stack),
            "settings": SettingsPage(self._theme_manager, self.page_stack),
        }
        # Allow artist navigation to filter songs.
        artists_page = self.pages["artists"]
        songs_page = self.pages["songs"]
        if hasattr(artists_page, "set_songs_page"):
            artists_page.set_songs_page(songs_page)
        for page in self.pages.values():
            self.page_stack.addWidget(page)

        body_layout.addWidget(content, 1)

        self.queue_panel = QueuePanel(self._theme_manager, self.audio_engine, body)
        self.queue_panel.setVisible(False)
        body_layout.addWidget(self.queue_panel)

        root_layout.addWidget(body, 1)

        self.scan_status = QWidget(root)
        self.scan_status.setObjectName("scanStatus")
        self.scan_status.setVisible(False)
        scan_layout = QHBoxLayout(self.scan_status)
        scan_layout.setContentsMargins(16, 6, 16, 6)
        scan_layout.setSpacing(10)
        self.scan_label = QLabel("Scanning music…", self.scan_status)
        self.scan_label.setObjectName("scanLabel")
        scan_layout.addWidget(self.scan_label, 1)
        self.scan_progress = QProgressBar(self.scan_status)
        self.scan_progress.setObjectName("scanProgress")
        self.scan_progress.setRange(0, 0)  # indeterminate until files discovered
        self.scan_progress.setTextVisible(False)
        self.scan_progress.setFixedWidth(160)
        scan_layout.addWidget(self.scan_progress)
        self.scan_cancel_button = QPushButton("Cancel", self.scan_status)
        self.scan_cancel_button.setObjectName("scanCancelButton")
        self.scan_cancel_button.clicked.connect(self.cancel_scan)
        scan_layout.addWidget(self.scan_cancel_button)
        root_layout.addWidget(self.scan_status)

        self.player_bar = PlayerBar(
            self._theme_manager, root, engine=self.audio_engine, library_db=self.library_db
        )
        self.player_bar.on_favorite_changed = lambda _tid, _fav: self.refresh_library_views()
        self.player_bar.queue_toggled.connect(self._toggle_queue_panel)
        self.player_bar.track_info_clicked.connect(lambda: self.navigate("now_playing"))
        self.player_bar.eq_requested.connect(lambda: self.navigate("equalizer"))
        root_layout.addWidget(self.player_bar)

        self.setCentralWidget(root)
        self.sidebar.navigation_requested.connect(self.navigate)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self.open_action = QAction("&Open Audio Files…", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.setToolTip("Open files for temporary playback")
        self.open_action.triggered.connect(self.open_audio_files)
        file_menu.addAction(self.open_action)

        file_menu.addSeparator()

        self.import_folder_action = QAction("Import Music &Folder…", self)
        self.import_folder_action.triggered.connect(self.import_music_folder)
        file_menu.addAction(self.import_folder_action)

        self.import_files_action = QAction("&Import Music Files…", self)
        self.import_files_action.triggered.connect(self.import_music_files)
        file_menu.addAction(self.import_files_action)

        file_menu.addSeparator()

        self.mini_player_action = QAction("Mini &Player", self)
        self.mini_player_action.triggered.connect(self.show_mini_player)
        file_menu.addAction(self.mini_player_action)

        file_menu.addSeparator()

        self.quit_action = QAction("&Quit", self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.quit_action.triggered.connect(self.quit_app)
        file_menu.addAction(self.quit_action)

        # Keep actions/shortcuts available but remove the visible top menu bar.
        self.menuBar().setVisible(False)

    # ------------------------------------------------------------------ import

    def open_audio_files(self) -> None:
        """Ask for local audio files with the native dialog and start playing."""
        music_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.MusicLocation
        )
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "Open audio files",
            music_dir,
            AUDIO_FILE_FILTER,
        )
        if paths:
            self.load_audio_files(paths)

    def load_audio_files(self, paths: list[str], autoplay: bool = True) -> bool:
        """Load explicit paths into the player (used by the dialog and tests)."""
        return self.audio_engine.open_files(paths, autoplay=autoplay)

    def import_music_folder(self) -> None:
        music_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.MusicLocation
        )
        folder = QFileDialog.getExistingDirectory(self, "Import music folder", music_dir)
        if folder:
            self.start_scan([folder])

    def import_music_files(self) -> None:
        music_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.MusicLocation
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import music files",
            music_dir,
            AUDIO_FILE_FILTER,
        )
        if paths:
            self.start_scan(paths)

    def _scan_registered_folders_if_enabled(self) -> None:
        if not bool(get_setting(self._theme_manager._settings, SCAN_ON_STARTUP_KEY, False)):
            return
        try:
            folders = self.library_db.get_library_folders()
        except Exception:
            folders = []
        existing = [f for f in folders if Path(f).exists()]
        if existing:
            self.start_scan(existing)

    def start_scan(self, paths: list[str]) -> None:
        self._last_scan_paths = [str(p) for p in paths]
        if self._scan_thread is not None and self._scan_thread.isRunning():
            self.scan_label.setText("A scan is already in progress.")
            self.scan_status.setVisible(True)
            return

        self.scan_status.setVisible(True)
        self.scan_progress.setRange(0, 0)
        self.scan_label.setText("Scanning music…")
        self.scan_cancel_button.setEnabled(True)

        self._scan_thread = QThread(self)
        self._scan_worker = MusicScannerWorker(
            db_path=self.library_db.db_path,
            artwork_dir=self.library_db.db_path.parent / "artwork",
        )
        self._scan_worker.set_paths(paths)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_thread.finished.connect(self._scan_thread.deleteLater)
        self._scan_thread.finished.connect(self._clear_scan_refs)
        self._scan_thread.start()

    def cancel_scan(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            self.scan_cancel_button.setEnabled(False)
            self.scan_label.setText("Cancelling scan…")

    def _clear_scan_refs(self) -> None:
        self._scan_thread = None
        self._scan_worker = None

    def _on_scan_progress(
        self, discovered: int, imported: int, skipped: int, failed: int, current: str
    ) -> None:
        if discovered > 0:
            self.scan_progress.setRange(0, max(discovered, 1))
            self.scan_progress.setValue(discovered)
        name = Path(current).name if current else ""
        suffix = f" — {name}" if name else ""
        self.scan_label.setText(
            f"Scanning: {discovered} found, {imported} imported, {skipped} skipped, {failed} failed{suffix}"
        )

    def _on_scan_error(self, message: str) -> None:
        # Keep last error visible briefly in label; full details in tooltip.
        self.scan_label.setToolTip(message)

    def _on_scan_finished(
        self, discovered: int, imported: int, skipped: int, failed: int, cancelled: bool
    ) -> None:
        status = "Scan cancelled" if cancelled else "Scan complete"
        self.scan_label.setText(
            f"{status}: {discovered} found, {imported} imported, {skipped} skipped, {failed} failed."
        )
        self.scan_progress.setRange(0, 1)
        self.scan_progress.setValue(1)
        self.scan_cancel_button.setEnabled(False)
        try:
            for p in getattr(self, "_last_scan_paths", []) or []:
                if Path(p).exists():
                    self.library_db.mark_library_folder_scanned(p)
        except Exception:
            pass
        self.refresh_library_views()
        self.scan_status.setVisible(True)

    # ----------------------------------------------------------------- library

    def refresh_library_views(self) -> None:
        for page in self.pages.values():
            refresh = getattr(page, "refresh_library", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass
        if hasattr(self, "player_bar") and hasattr(self.player_bar, "refresh_favorite_state"):
            try:
                self.player_bar.refresh_favorite_state()
            except Exception:
                pass

    def _on_track_played(self, track) -> None:
        if track is None:
            return
        # Deferred: track_changed is delivered to every connected UI widget in
        # connection order, and this slot is connected first (line ~102), so a
        # synchronous DB write here would delay the player bar / Now Playing /
        # MPRIS updates by the duration of the write. A zero-delay single-shot
        # still runs after the current signal emission finishes, and queued
        # timers fire FIFO, so rapid skips keep their play-count order.
        QTimer.singleShot(0, lambda t=track: self._record_played(t))

    def _record_played(self, track) -> None:
        try:
            self.library_db.mark_played(
                track.path, datetime.now(timezone.utc).isoformat()
            )
            # Page rebuilds are comparatively expensive; deferring them keeps
            # the track-change path responsive (title/artwork/MPRIS update at
            # once).
            self._schedule_library_view_refresh()
        except RuntimeError:
            # Deferred singleShot fired after the main window was deleted.
            pass
        except Exception:
            pass

    def _schedule_library_view_refresh(self) -> None:
        if not hasattr(self, "_library_view_timer") or self._library_view_timer is None:
            self._library_view_timer = QTimer(self)
            self._library_view_timer.setSingleShot(True)
            self._library_view_timer.setInterval(250)
            self._library_view_timer.timeout.connect(self._refresh_home_and_recent)
        self._library_view_timer.start()

    def _refresh_home_and_recent(self) -> None:
        for key in ("home", "recent"):
            page = self.pages.get(key)
            refresh = getattr(page, "refresh_library", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass

    # --------------------------------------------------------------- navigation

    def navigate(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        current = self.page_stack.currentWidget()
        self.page_stack.setCurrentWidget(page)
        self.sidebar.set_current(key)
        self._current_page_key = key
        # One authoritative seek control at a time: the immersive page owns it
        # while visible, the persistent bar owns it everywhere else.
        if hasattr(self, "player_bar"):
            self.player_bar.set_seek_visible(key != "now_playing")

        # Subtle fade-in on page transition (respect reduced motion/offscreen).
        reduce = bool(getattr(self._theme_manager, "reduced_motion", False))
        try:
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.platformName() == "offscreen":
                reduce = True
        except Exception:
            pass
        if reduce or page is current:
            return
        try:
            effect = page.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(page)
                page.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(140)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda: page.setGraphicsEffect(None))
            old_anim = getattr(self, "_page_fade_anim", None)
            if old_anim is not None:
                try:
                    old_anim.stop()
                except Exception:
                    pass
            self._page_fade_anim = anim
            anim.start()
        except Exception:
            try:
                page.setGraphicsEffect(None)
            except Exception:
                pass

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if hasattr(self, "_bg_host"):
            self._sync_content_background_geometry()
            self._bg_update_timer.start()
        if not hasattr(self, "sidebar"):
            return
        collapsed = event.size().width() < SIDEBAR_AUTO_COLLAPSE_WIDTH
        if collapsed != self._auto_collapsed:
            self._auto_collapsed = collapsed
            self.sidebar.set_collapsed(collapsed)

    def _on_theme_changed(self, _theme: str) -> None:
        self._refresh_theme()

    def _refresh_theme(self) -> None:
        colors: ThemeColors = self._theme_manager.colors
        for widget in self.findChildren(QWidget):
            refresh = getattr(widget, "refresh_theme", None)
            if callable(refresh):
                refresh(colors)
        self._update_content_background()

    def _current_artwork_path(self) -> str | None:
        track = self.audio_engine.current_track
        if track is None:
            return None
        try:
            cur = self.audio_engine.queue_manager.current_item
            if cur is not None and getattr(cur, "artwork_path", None):
                return cur.artwork_path
        except Exception:
            pass
        try:
            rec = self.library_db.get_track_by_path(str(track.path))
            return rec.artwork_path if rec else None
        except Exception:
            return None

    def _sync_content_background_geometry(self) -> None:
        host = getattr(self, "_bg_host", None)
        if host is None:
            return
        rect = host.rect()
        self._content_bg.setGeometry(rect)
        self._content_overlay.setGeometry(rect)
        self._content_bg.lower()
        self._content_overlay.lower()

    def _update_content_background(self, *_args) -> None:
        host = getattr(self, "_bg_host", None)
        if host is None:
            return
        self._sync_content_background_geometry()
        art = self._current_artwork_path()
        size = host.size()
        transparent_areas = "QWidget#appRoot, QWidget#bodyArea, QWidget#contentArea, QStackedWidget#pageStack { background: transparent; }"
        if art and size.width() > 10 and size.height() > 10:
            # Render at capped size; QLabel scales it. Avoids resize-cost spikes.
            max_w, max_h = 1280, 720
            scale = min(max_w / max(1, size.width()), max_h / max(1, size.height()), 1.0)
            target = QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale)))
            pix = blurred_artwork_pixmap(art, target, blur_radius=28.0)
            if pix is not None:
                self._content_bg.setPixmap(pix)
                dark = self._theme_manager.effective_theme == "dark"
                overlay = "background-color: rgba(12,13,16,0.42);" if dark else "background-color: rgba(245,243,239,0.42);"
                self._content_overlay.setStyleSheet(overlay)
                host.setStyleSheet(transparent_areas)
                return
        self._content_bg.clear()
        self._content_bg.setStyleSheet("background: transparent;")
        self._content_overlay.setStyleSheet("background: transparent;")
        host.setStyleSheet("")

    # ------------------------------------------------------------------- queue

    def _toggle_queue_panel(self, visible: bool | None = None) -> None:
        if visible is None:
            visible = not self.queue_panel.isVisible()
        self.queue_panel.setVisible(bool(visible))
        self.player_bar.set_queue_visible(self.queue_panel.isVisible())
        if self.queue_panel.isVisible():
            self.queue_panel.refresh_queue()

    def _setup_shortcuts(self) -> None:
        # Space: play/pause, but not while typing in text inputs.
        self._sc_play = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        self._sc_play.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_play.activated.connect(self._shortcut_play_pause)

        self._sc_next = QShortcut(QKeySequence("Ctrl+Right"), self)
        self._sc_next.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_next.activated.connect(self.audio_engine.next_track)

        self._sc_prev = QShortcut(QKeySequence("Ctrl+Left"), self)
        self._sc_prev.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_prev.activated.connect(self.audio_engine.previous_track)

        self._sc_vol_up = QShortcut(QKeySequence("Ctrl+Up"), self)
        self._sc_vol_up.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_vol_up.activated.connect(lambda: self.audio_engine.set_volume(self.audio_engine.volume + 5))

        self._sc_vol_down = QShortcut(QKeySequence("Ctrl+Down"), self)
        self._sc_vol_down.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_vol_down.activated.connect(lambda: self.audio_engine.set_volume(self.audio_engine.volume - 5))

        self._sc_mute = QShortcut(QKeySequence("Ctrl+M"), self)
        self._sc_mute.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_mute.activated.connect(self.audio_engine.toggle_mute)

        self._sc_shuffle = QShortcut(QKeySequence("Ctrl+S"), self)
        self._sc_shuffle.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_shuffle.activated.connect(self._shortcut_shuffle)

        self._sc_repeat = QShortcut(QKeySequence("Ctrl+R"), self)
        self._sc_repeat.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_repeat.activated.connect(self._shortcut_repeat)

        self._sc_queue = QShortcut(QKeySequence("Ctrl+Q"), self)
        self._sc_queue.setContext(Qt.ShortcutContext.WindowShortcut)
        self._sc_queue.activated.connect(lambda: self._toggle_queue_panel())

    def _is_text_input_focused(self) -> bool:
        w = QApplication.focusWidget()
        if w is None:
            return False
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox
        return isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox))

    def _shortcut_play_pause(self) -> None:
        if self._is_text_input_focused():
            return
        self.audio_engine.toggle_play_pause()

    def _shortcut_shuffle(self) -> None:
        if self._is_text_input_focused():
            return
        self.audio_engine.queue_manager.toggle_shuffle()

    def _shortcut_repeat(self) -> None:
        if self._is_text_input_focused():
            return
        self.audio_engine.queue_manager.cycle_repeat_mode()

    def _schedule_queue_save(self) -> None:
        if hasattr(self, "_queue_save_timer"):
            self._queue_save_timer.start()

    def _on_position_for_save(self, pos: int) -> None:
        # Save periodically (every ~15s) while playing, not on every tick.
        if not hasattr(self, "_last_queue_save_pos"):
            self._last_queue_save_pos = 0
        if abs(int(pos) - int(self._last_queue_save_pos)) >= 15000:
            self._last_queue_save_pos = int(pos)
            self._schedule_queue_save()

    def _save_queue_state(self) -> None:
        try:
            settings = self._theme_manager._settings
            if not bool(get_setting(settings, REMEMBER_STATE_KEY, True)):
                return
            qm = self.audio_engine.queue_manager
            items = []
            for i, item in enumerate(qm.items):
                items.append({
                    "queue_order": i,
                    "track_id": item.track_id,
                    "file_path": str(item.path),
                    "title": item.title,
                    "artist": item.artist,
                    "album": item.album,
                    "duration": item.duration,
                    "artwork_path": item.artwork_path,
                })
            current = qm.current_item
            self.library_db.save_queue_state(
                items=items,
                current_queue_index=qm.current_index,
                current_position_ms=self.audio_engine.position,
                shuffle_enabled=qm.shuffle,
                repeat_mode=qm.repeat_mode,
                current_file_path=str(current.path) if current else None,
            )
        except Exception:
            pass

    def _restore_queue_state(self) -> bool:
        settings = self._theme_manager._settings
        remember = bool(get_setting(settings, REMEMBER_STATE_KEY, True))
        resume_pos = bool(get_setting(settings, RESUME_POSITION_KEY, True))
        if not remember:
            self._apply_playback_defaults()
            return False
        try:
            state = self.library_db.load_queue_state()
        except Exception:
            state = None
        if not state or not state.get("items"):
            self._apply_playback_defaults()
            return False
        items = state["items"]
        qm = self.audio_engine.queue_manager
        qm.restore(
            items,
            current_index=state.get("current_queue_index", 0),
            shuffle=bool(state.get("shuffle_enabled", False)),
            repeat=str(state.get("repeat_mode", "off")),
        )
        current = qm.current_item
        if current is not None:
            self.audio_engine._load_item(current, autoplay=False)
            pos = int(state.get("current_position_ms", 0) or 0)
            if pos > 0 and resume_pos:
                QTimer.singleShot(150, lambda p=pos: self.audio_engine.set_position(p))
        self.queue_panel.refresh_queue()
        return True

    def _apply_playback_defaults(self) -> None:
        settings = self._theme_manager._settings
        try:
            self.audio_engine.queue_manager.set_shuffle(bool(get_setting(settings, DEFAULT_SHUFFLE_KEY, False)))
        except Exception:
            pass
        try:
            self.audio_engine.queue_manager.set_repeat_mode(str(get_setting(settings, DEFAULT_REPEAT_KEY, "off")))
        except Exception:
            pass

    # -------------------------------------------------------------- mini player

    def show_mini_player(self) -> None:
        if self._mini_player is None:
            self._mini_player = MiniPlayerWindow(
                self._theme_manager,
                self.audio_engine,
                self.library_db,
                on_restore=self.restore_from_mini_player,
                parent=None,
            )
            self._mini_player.destroyed.connect(lambda *_: setattr(self, "_mini_player", None))
        self._mini_player.refresh_theme(self._theme_manager.colors)
        reduce = bool(getattr(self._theme_manager, "reduced_motion", False))
        try:
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.platformName() == "offscreen":
                reduce = True
        except Exception:
            pass
        if not reduce:
            try:
                self._mini_player.setWindowOpacity(0.0)
            except Exception:
                pass
        self._mini_player.show()
        self._mini_player.raise_()
        self._mini_player.activateWindow()
        if not reduce:
            try:
                anim = QPropertyAnimation(self._mini_player, b"windowOpacity", self)
                anim.setDuration(140)
                anim.setStartValue(0.0)
                anim.setEndValue(1.0)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._mini_fade_anim = anim
                anim.start()
            except Exception:
                try:
                    self._mini_player.setWindowOpacity(1.0)
                except Exception:
                    pass
        self.hide()

    def restore_from_mini_player(self) -> None:
        self.show_from_tray()
        mp = self._mini_player
        if mp is None:
            return
        reduce = bool(getattr(self._theme_manager, "reduced_motion", False))
        try:
            from PySide6.QtGui import QGuiApplication
            if QGuiApplication.platformName() == "offscreen":
                reduce = True
        except Exception:
            pass
        if reduce:
            mp.hide()
            return
        try:
            anim = QPropertyAnimation(mp, b"windowOpacity", self)
            anim.setDuration(120)
            anim.setStartValue(mp.windowOpacity())
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InCubic)
            def _finish():
                try:
                    mp.hide()
                    mp.setWindowOpacity(1.0)
                except Exception:
                    pass
            anim.finished.connect(_finish)
            self._mini_fade_anim = anim
            anim.start()
        except Exception:
            mp.hide()

    # ------------------------------------------------------ desktop integration

    def _start_desktop_integration(self) -> None:
        try:
            self.mpris_service.set_callbacks(raise_cb=self.show_from_tray, quit_cb=self.quit_app)
            self.mpris_service.start()
        except Exception:
            pass
        try:
            self.tray_service.start(show_cb=self.show_from_tray, quit_cb=self.quit_app)
        except Exception:
            pass

    def _on_track_changed_notify(self, track) -> None:
        if track is None:
            return
        if not self._notifications_enabled:
            return
        # Deferred off the signal path: the D-Bus notification call can block
        # for tens of ms and would otherwise delay UI/MPRIS track updates.
        QTimer.singleShot(0, lambda t=track: self._send_track_notification(t))

    def _send_track_notification(self, track) -> None:
        if track is None or not self._notifications_enabled:
            return
        art = None
        try:
            rec = self.library_db.get_track_by_path(str(track.path))
            art = rec.artwork_path if rec else None
        except Exception:
            art = None
        try:
            self.notification_service.notify_track(track.title, track.artist, "", art)
        except RuntimeError:
            # Deferred singleShot fired after the main window was deleted.
            pass
        except Exception:
            pass

    @property
    def notifications_enabled(self) -> bool:
        return self._notifications_enabled

    @property
    def close_to_tray(self) -> bool:
        return self._close_to_tray

    def set_notifications_enabled(self, enabled: bool) -> None:
        self._notifications_enabled = bool(enabled)
        self.notification_service.set_enabled(self._notifications_enabled)
        set_setting(self._theme_manager._settings, PLAYBACK_NOTIFICATIONS_KEY, self._notifications_enabled)
        self._theme_manager._settings.sync()

    def set_close_to_tray(self, enabled: bool) -> None:
        self._close_to_tray = bool(enabled)
        set_setting(self._theme_manager._settings, CLOSE_TO_TRAY_KEY, self._close_to_tray)
        self._theme_manager._settings.sync()

    def _on_volume_changed_save(self, volume: int) -> None:
        try:
            set_setting(self._theme_manager._settings, VOLUME_KEY, int(volume))
        except Exception:
            pass

    def show_from_tray(self) -> None:
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        tray_active = bool(getattr(self.tray_service, "_tray", None) is not None)
        if (not self._quitting) and self._close_to_tray and tray_active:
            event.ignore()
            self.hide()
            return
        try:
            self._save_queue_state()
        except Exception:
            pass
        try:
            self.mpris_service.shutdown()
        except Exception:
            pass
        try:
            self.tray_service.shutdown()
        except Exception:
            pass
        try:
            if self._mini_player is not None:
                self._mini_player._on_restore = None
                self._mini_player.close()
                self._mini_player = None
        except Exception:
            pass
        self.cancel_scan()
        thread = self._scan_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(2000)
        super().closeEvent(event)
