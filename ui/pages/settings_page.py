"""Settings page: appearance, playback, library, desktop integration, cache, about."""

from __future__ import annotations

import platform
from pathlib import Path

import PySide6
from PySide6.QtCore import QSize, Qt, qVersion
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core import __version__
from core.app_settings import (
    AMBIENT_ARTWORK_KEY,
    ARTWORK_CACHE_LIMIT_MB_KEY,
    DEFAULT_REPEAT_KEY,
    DEFAULT_SHUFFLE_KEY,
    REMEMBER_STATE_KEY,
    RESUME_POSITION_KEY,
    SCAN_ON_STARTUP_KEY,
    VOLUME_KEY,
    get_setting,
    set_setting,
)
from core.theme_manager import DARK, LIGHT, SYSTEM, ThemeColors, ThemeManager
from services.artwork_cache import ArtworkCache
from ui.components.section_header import SectionHeader
from ui.icons import icon
from ui.pages.base_page import BasePage


def _fmt_bytes(num: int) -> str:
    size = float(max(0, int(num)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class SettingsPage(BasePage):
    def __init__(self, theme_manager: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(
            "Settings",
            "Personalize ISAI, manage your library, and keep playback smooth.",
            parent=parent,
        )
        self._theme_manager = theme_manager
        self.body.setSpacing(14)
        self._build_appearance()
        self._build_playback()
        self._build_library()
        self._build_desktop()
        self._build_storage()
        self._build_about()
        self.body.addStretch(1)

        theme_manager.theme_changed.connect(self._on_theme_changed)
        theme_manager.reduced_motion_changed.connect(self._on_reduced_motion_changed)
        self.refresh_theme(theme_manager.colors)
        self.refresh_library()

    # ---------------------------------------------------------------- appearance

    def _build_appearance(self) -> None:
        self.body.addWidget(SectionHeader("Appearance", parent=self))
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        theme_control = QWidget(card)
        theme_row = QHBoxLayout(theme_control)
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.setSpacing(8)
        self.theme_buttons: dict[str, QPushButton] = {}
        self._theme_group = QButtonGroup(self)
        self._theme_group.setExclusive(True)
        options = [(LIGHT, "Light", "sun"), (DARK, "Dark", "moon")]
        if self._theme_manager.supports_system_theme():
            options.append((SYSTEM, "System", "settings"))
        for key, label, icon_name in options:
            button = QPushButton(label, theme_control)
            button.setObjectName("themeOption")
            button.setCheckable(True)
            button.setIconSize(QSize(16, 16))
            button.setProperty("theme", key)
            button.setProperty("iconName", icon_name)
            button.clicked.connect(lambda _=False, selected=key: self._theme_manager.set_theme(selected))
            self._theme_group.addButton(button)
            self.theme_buttons[key] = button
            theme_row.addWidget(button)
        layout.addWidget(self._make_row(
            "Theme",
            "Choose Dark, Light, or System. Changes apply immediately and persist across restarts.",
            theme_control,
        ))

        self._palette_preview = QWidget(card)
        preview = QHBoxLayout(self._palette_preview)
        preview.setContentsMargins(0, 0, 0, 0)
        preview.setSpacing(6)
        self._swatches: dict[str, QLabel] = {}
        for token in ("bg", "surface", "accent"):
            swatch = QLabel(self._palette_preview)
            swatch.setFixedSize(22, 22)
            self._swatches[token] = swatch
            preview.addWidget(swatch)
        self._palette_name = QLabel(self._palette_preview)
        self._palette_name.setObjectName("settingsValue")
        preview.addWidget(self._palette_name)
        layout.addWidget(self._make_row(
            "Palette",
            "The active color palette currently applied to ISAI.",
            self._palette_preview,
        ))

        self.reduced_motion_checkbox = QCheckBox("Reduce motion", card)
        self.reduced_motion_checkbox.toggled.connect(self._theme_manager.set_reduced_motion)
        layout.addWidget(self._make_row(
            "Motion",
            "Reduce nonessential animations for accessibility and lower distraction.",
            self.reduced_motion_checkbox,
        ))

        self.ambient_checkbox = QCheckBox("Enable artwork ambient colors", card)
        self.ambient_checkbox.toggled.connect(self._on_ambient_toggled)
        layout.addWidget(self._make_row(
            "Ambient artwork",
            "Use subtle artwork-inspired ambient accents on immersive surfaces.",
            self.ambient_checkbox,
            last=True,
        ))
        self.body.addWidget(card)

    # ------------------------------------------------------------------ playback

    def _build_playback(self) -> None:
        self.body.addWidget(SectionHeader("Playback", parent=self))
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        vol_wrap = QWidget(card)
        vol_layout = QHBoxLayout(vol_wrap)
        vol_layout.setContentsMargins(0, 0, 0, 0)
        vol_layout.setSpacing(10)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal, vol_wrap)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(180)
        self.volume_slider.valueChanged.connect(self._on_default_volume_changed)
        self.volume_value = QLabel("70%", vol_wrap)
        self.volume_value.setObjectName("settingsValue")
        vol_layout.addWidget(self.volume_slider)
        vol_layout.addWidget(self.volume_value)
        layout.addWidget(self._make_row(
            "Default volume",
            "Volume used for playback. Changes apply to the active engine and persist.",
            vol_wrap,
        ))

        self.resume_checkbox = QCheckBox("Resume playback position", card)
        self.resume_checkbox.toggled.connect(lambda v: self._set_bool(RESUME_POSITION_KEY, v))
        layout.addWidget(self._make_row(
            "Resume position",
            "Restore the last playback position when remembering playback state.",
            self.resume_checkbox,
        ))

        self.remember_state_checkbox = QCheckBox("Remember playback state", card)
        self.remember_state_checkbox.toggled.connect(lambda v: self._set_bool(REMEMBER_STATE_KEY, v))
        layout.addWidget(self._make_row(
            "Remember state",
            "Restore queue, current track, shuffle, and repeat on startup.",
            self.remember_state_checkbox,
        ))

        self.repeat_combo = QComboBox(card)
        self.repeat_combo.addItems(["Off", "All", "One"])
        self.repeat_combo.currentTextChanged.connect(self._on_repeat_changed)
        layout.addWidget(self._make_row(
            "Default repeat",
            "Repeat mode used when no remembered queue state is restored.",
            self.repeat_combo,
        ))

        self.shuffle_checkbox = QCheckBox("Shuffle by default", card)
        self.shuffle_checkbox.toggled.connect(lambda v: self._set_bool(DEFAULT_SHUFFLE_KEY, v))
        layout.addWidget(self._make_row(
            "Default shuffle",
            "Shuffle used when no remembered queue state is restored.",
            self.shuffle_checkbox,
            last=True,
        ))
        self.body.addWidget(card)

    # ------------------------------------------------------------------- library

    def _build_library(self) -> None:
        self.body.addWidget(SectionHeader("Library", parent=self))
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        folders_wrap = QWidget(card)
        folders_layout = QVBoxLayout(folders_wrap)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        folders_layout.setSpacing(8)
        self.folder_list = QListWidget(folders_wrap)
        self.folder_list.setMaximumHeight(140)
        folders_layout.addWidget(self.folder_list)
        folder_btns = QHBoxLayout()
        folder_btns.setSpacing(8)
        self.add_folder_btn = QPushButton("Add folder", folders_wrap)
        self.add_folder_btn.setObjectName("secondaryButton")
        self.add_folder_btn.clicked.connect(self._add_library_folder)
        self.remove_folder_btn = QPushButton("Remove selected", folders_wrap)
        self.remove_folder_btn.setObjectName("secondaryButton")
        self.remove_folder_btn.clicked.connect(self._remove_library_folder)
        self.rescan_btn = QPushButton("Rescan folders", folders_wrap)
        self.rescan_btn.setObjectName("secondaryButton")
        self.rescan_btn.clicked.connect(self._rescan_library_folders)
        folder_btns.addWidget(self.add_folder_btn)
        folder_btns.addWidget(self.remove_folder_btn)
        folder_btns.addWidget(self.rescan_btn)
        folder_btns.addStretch(1)
        folders_layout.addLayout(folder_btns)
        layout.addWidget(self._make_row(
            "Music folders",
            "Register folders for scanning. Removing a folder registration does not delete your music files.",
            folders_wrap,
        ))

        self.scan_startup_checkbox = QCheckBox("Scan registered folders at startup", card)
        self.scan_startup_checkbox.toggled.connect(lambda v: self._set_bool(SCAN_ON_STARTUP_KEY, v))
        layout.addWidget(self._make_row(
            "Startup scan",
            "Optionally rescan registered folders in the background after launch.",
            self.scan_startup_checkbox,
        ))

        self.library_stats_label = QLabel("", card)
        self.library_stats_label.setObjectName("settingsValue")
        self.library_stats_label.setWordWrap(True)
        layout.addWidget(self._make_row(
            "Library information",
            "Total songs, albums, and artists currently in the ISAI library database.",
            self.library_stats_label,
            last=True,
        ))
        self.body.addWidget(card)

    # ------------------------------------------------------------------- desktop

    def _build_desktop(self) -> None:
        self.body.addWidget(SectionHeader("Notifications and Linux Integration", parent=self))
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.notifications_checkbox = QCheckBox("Show track-change notifications", card)
        self.notifications_checkbox.toggled.connect(self._on_notifications_toggled)
        layout.addWidget(self._make_row(
            "Notifications",
            "Show a desktop notification when a new track starts playing.",
            self.notifications_checkbox,
        ))

        self.close_to_tray_checkbox = QCheckBox("Minimize to tray on close", card)
        self.close_to_tray_checkbox.toggled.connect(self._on_close_to_tray_toggled)
        layout.addWidget(self._make_row(
            "Close behavior",
            "When the system tray is available, closing the window can keep ISAI running in the tray.",
            self.close_to_tray_checkbox,
        ))

        self.tray_status_label = QLabel("", card)
        self.tray_status_label.setObjectName("settingsValue")
        layout.addWidget(self._make_row(
            "System tray",
            "Tray integration depends on desktop environment support.",
            self.tray_status_label,
        ))

        self.mpris_status_label = QLabel("", card)
        self.mpris_status_label.setObjectName("settingsValue")
        layout.addWidget(self._make_row(
            "MPRIS integration",
            "Linux media controls use MPRIS2 over D-Bus when available.",
            self.mpris_status_label,
            last=True,
        ))
        self.body.addWidget(card)

    # ------------------------------------------------------------------- storage

    def _build_storage(self) -> None:
        self.body.addWidget(SectionHeader("Storage and Cache", parent=self))
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.cache_location_label = QLabel("", card)
        self.cache_location_label.setObjectName("settingsValue")
        self.cache_location_label.setWordWrap(True)
        layout.addWidget(self._make_row(
            "Artwork cache location",
            "Extracted artwork is stored in the user data directory.",
            self.cache_location_label,
        ))

        self.cache_size_label = QLabel("", card)
        self.cache_size_label.setObjectName("settingsValue")
        layout.addWidget(self._make_row(
            "Artwork cache size",
            "Current size of artwork cache files on disk.",
            self.cache_size_label,
        ))

        self.db_info_label = QLabel("", card)
        self.db_info_label.setObjectName("settingsValue")
        self.db_info_label.setWordWrap(True)
        layout.addWidget(self._make_row(
            "Database information",
            "SQLite library database path and size. The database is never cleared by cache cleanup.",
            self.db_info_label,
        ))

        cache_controls = QWidget(card)
        cache_btns = QHBoxLayout(cache_controls)
        cache_btns.setContentsMargins(0, 0, 0, 0)
        cache_btns.setSpacing(8)
        self.clear_cache_btn = QPushButton("Clear artwork cache", cache_controls)
        self.clear_cache_btn.setObjectName("secondaryButton")
        self.clear_cache_btn.clicked.connect(self._clear_artwork_cache)
        self.clear_temp_btn = QPushButton("Clear temp files", cache_controls)
        self.clear_temp_btn.setObjectName("secondaryButton")
        self.clear_temp_btn.clicked.connect(self._clear_temp_files)
        cache_btns.addWidget(self.clear_cache_btn)
        cache_btns.addWidget(self.clear_temp_btn)
        cache_btns.addStretch(1)
        layout.addWidget(self._make_row(
            "Cache cleanup",
            "Clears only artwork cache or ISAI temporary files. Music files and the library database are not deleted.",
            cache_controls,
            last=True,
        ))
        self.body.addWidget(card)

    # --------------------------------------------------------------------- about

    def _build_about(self) -> None:
        self.body.addWidget(SectionHeader("About ISAI", parent=self))
        card = QFrame(self)
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._make_row(
            "Application",
            "ISAI — Your music. Your space. An independent, lightweight, Linux-native music player.",
            self._value_label(f"ISAI {__version__}"),
        ))
        layout.addWidget(self._make_row(
            "Framework",
            "Graphics toolkit and Qt binding.",
            self._value_label(f"PySide6 {PySide6.__version__} · Qt {qVersion()}"),
        ))
        layout.addWidget(self._make_row(
            "Runtime",
            "Python runtime and platform.",
            self._value_label(f"Python {platform.python_version()} · {platform.system() or 'Linux'}"),
            last=True,
        ))
        self.body.addWidget(card)

    # --------------------------------------------------------------- UI helpers

    def _make_row(self, title: str, description: str, control: QWidget, last: bool = False) -> QFrame:
        row = QFrame(self)
        row.setObjectName("settingsRow")
        row.setProperty("last", "true" if last else "false")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(20)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title_label = QLabel(title, row)
        title_label.setObjectName("settingsTitle")
        text_layout.addWidget(title_label)
        description_label = QLabel(description, row)
        description_label.setObjectName("settingsDescription")
        description_label.setWordWrap(True)
        text_layout.addWidget(description_label)
        layout.addLayout(text_layout, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsValue")
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return label

    def _settings(self):
        return self._theme_manager._settings

    def _set_bool(self, key: str, value: bool) -> None:
        set_setting(self._settings(), key, bool(value))

    # ------------------------------------------------------------------ actions

    def _on_theme_changed(self, _theme: str) -> None:
        self.refresh_theme(self._theme_manager.colors)

    def _on_reduced_motion_changed(self, _enabled: bool) -> None:
        self.reduced_motion_checkbox.blockSignals(True)
        self.reduced_motion_checkbox.setChecked(bool(_enabled))
        self.reduced_motion_checkbox.blockSignals(False)

    def _on_ambient_toggled(self, enabled: bool) -> None:
        self._set_bool(AMBIENT_ARTWORK_KEY, bool(enabled))

    def _on_default_volume_changed(self, value: int) -> None:
        value = max(0, min(100, int(value)))
        self.volume_value.setText(f"{value}%")
        set_setting(self._settings(), VOLUME_KEY, value)
        win = self.window()
        engine = getattr(win, "audio_engine", None)
        if engine is not None:
            try:
                engine.set_volume(value)
            except Exception:
                pass

    def _on_repeat_changed(self, text: str) -> None:
        mode = {"Off": "off", "All": "all", "One": "one"}.get(text, "off")
        set_setting(self._settings(), DEFAULT_REPEAT_KEY, mode)

    def _on_notifications_toggled(self, enabled: bool) -> None:
        win = self.window()
        fn = getattr(win, "set_notifications_enabled", None)
        if callable(fn):
            fn(enabled)
        else:
            self._set_bool("desktop/notifications_enabled", bool(enabled))

    def _on_close_to_tray_toggled(self, enabled: bool) -> None:
        win = self.window()
        fn = getattr(win, "set_close_to_tray", None)
        if callable(fn):
            fn(enabled)
        else:
            self._set_bool("desktop/close_to_tray", bool(enabled))

    def _add_library_folder(self) -> None:
        win = self.window()
        db = getattr(win, "library_db", None)
        if db is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Add music folder", str(Path.home()))
        if not folder:
            return
        try:
            db.add_library_folder(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Add folder", str(exc))
        self.refresh_library()

    def _remove_library_folder(self) -> None:
        win = self.window()
        db = getattr(win, "library_db", None)
        if db is None:
            return
        item = self.folder_list.currentItem()
        if item is None:
            return
        folder = item.text()
        confirm = QMessageBox.question(
            self,
            "Remove music folder",
            f"Remove this folder registration from ISAI?\n\n{folder}\n\nYour music files and library database will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            db.remove_library_folder(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Remove folder", str(exc))
        self.refresh_library()

    def _rescan_library_folders(self) -> None:
        win = self.window()
        db = getattr(win, "library_db", None)
        if db is None:
            return
        folders = []
        try:
            folders = db.get_library_folders()
        except Exception:
            folders = []
        if not folders:
            QMessageBox.information(self, "Rescan folders", "No registered music folders. Add a folder first.")
            return
        start_scan = getattr(win, "start_scan", None)
        if callable(start_scan):
            start_scan(folders)

    def _clear_artwork_cache(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Clear artwork cache",
            "Clear extracted artwork cache files?\n\nThis will not delete your music files or the library database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        win = self.window()
        db = getattr(win, "library_db", None)
        cache = ArtworkCache()
        cache_dir = str(cache.cache_dir)
        files, freed = cache.clear()
        # Remove stale artwork paths that pointed into the cleared cache.
        try:
            if db is not None:
                with db.connect() as conn:
                    conn.execute(
                        "UPDATE tracks SET artwork_path = NULL WHERE artwork_path IS NOT NULL AND artwork_path LIKE ?",
                        (cache_dir + '%',),
                    )
        except Exception:
            pass
        self.refresh_library()
        QMessageBox.information(self, "Artwork cache cleared", f"Removed {files} file(s), freed {_fmt_bytes(freed)}.")

    def _clear_temp_files(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Clear temporary files",
            "Clear ISAI temporary files in /tmp/opencode where safe?\n\nThis will not delete your music files or the library database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        removed = 0
        freed = 0
        for base in [Path("/tmp/opencode")]:
            if not base.exists():
                continue
            for p in base.glob("isai*"):
                try:
                    if p.is_file():
                        size = p.stat().st_size
                        p.unlink()
                        removed += 1
                        freed += size
                except Exception:
                    pass
        self.refresh_library()
        QMessageBox.information(self, "Temporary files", f"Removed {removed} file(s), freed {_fmt_bytes(freed)}.")

    # ------------------------------------------------------------------- refresh

    def refresh_library(self) -> None:
        win = self.window()
        db = getattr(win, "library_db", None)
        # Library folders
        self.folder_list.clear()
        if db is not None:
            try:
                for folder in db.get_library_folders():
                    self.folder_list.addItem(QListWidgetItem(folder))
            except Exception:
                pass
        # Stats
        if db is not None:
            try:
                stats = db.get_library_stats()
                self.library_stats_label.setText(
                    f"{stats['tracks']} songs · {stats['albums']} albums · {stats['artists']} artists\n"
                    f"{stats['playlists']} playlists · {stats['favorites']} favorites"
                )
            except Exception:
                self.library_stats_label.setText("Library information unavailable.")
        else:
            self.library_stats_label.setText("Library information unavailable.")
        # Cache/storage
        try:
            cache = ArtworkCache()
            self.cache_location_label.setText(str(cache.cache_dir))
            self.cache_size_label.setText(_fmt_bytes(cache.cache_size_bytes()))
        except Exception:
            self.cache_location_label.setText("Unavailable")
            self.cache_size_label.setText("Unavailable")
        try:
            if db is not None:
                self.db_info_label.setText(f"{db.db_path}\n{_fmt_bytes(db.database_file_size())}")
        except Exception:
            pass
        self._sync_desktop_settings()
        self._sync_playback_settings()

    def _sync_playback_settings(self) -> None:
        s = self._settings()
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(int(get_setting(s, VOLUME_KEY, 70)))
        self.volume_slider.blockSignals(False)
        self.volume_value.setText(f"{int(get_setting(s, VOLUME_KEY, 70))}%")
        for cb, key in [
            (self.resume_checkbox, RESUME_POSITION_KEY),
            (self.remember_state_checkbox, REMEMBER_STATE_KEY),
            (self.shuffle_checkbox, DEFAULT_SHUFFLE_KEY),
        ]:
            cb.blockSignals(True)
            cb.setChecked(bool(get_setting(s, key, False if key == DEFAULT_SHUFFLE_KEY else True)))
            cb.blockSignals(False)
        self.ambient_checkbox.blockSignals(True)
        self.ambient_checkbox.setChecked(bool(get_setting(s, AMBIENT_ARTWORK_KEY, True)))
        self.ambient_checkbox.blockSignals(False)
        self.scan_startup_checkbox.blockSignals(True)
        self.scan_startup_checkbox.setChecked(bool(get_setting(s, SCAN_ON_STARTUP_KEY, False)))
        self.scan_startup_checkbox.blockSignals(False)
        repeat = str(get_setting(s, DEFAULT_REPEAT_KEY, "off"))
        label = {"off": "Off", "all": "All", "one": "One"}.get(repeat, "Off")
        self.repeat_combo.blockSignals(True)
        self.repeat_combo.setCurrentText(label)
        self.repeat_combo.blockSignals(False)

    def _sync_desktop_settings(self) -> None:
        win = self.window()
        notif = bool(getattr(win, "notifications_enabled", True))
        close_tray = bool(getattr(win, "close_to_tray", True))
        tray_available = False
        mpris_active = False
        try:
            tray_available = bool(getattr(getattr(win, "tray_service", None), "available", False))
        except Exception:
            pass
        try:
            mpris_active = bool(getattr(getattr(win, "mpris_service", None), "_registered", False))
        except Exception:
            pass
        self.notifications_checkbox.blockSignals(True)
        self.notifications_checkbox.setChecked(notif)
        self.notifications_checkbox.blockSignals(False)
        self.close_to_tray_checkbox.blockSignals(True)
        self.close_to_tray_checkbox.setChecked(close_tray)
        self.close_to_tray_checkbox.setEnabled(tray_available)
        self.close_to_tray_checkbox.blockSignals(False)
        self.tray_status_label.setText("Available" if tray_available else "Unavailable on this desktop")
        self.mpris_status_label.setText("Active" if mpris_active else "Unavailable or not registered")

    def refresh_theme(self, colors: ThemeColors) -> None:
        for key, button in self.theme_buttons.items():
            button.setChecked(key == self._theme_manager.theme)
            color = colors.accent_text if key == self._theme_manager.theme else colors.text_muted
            icon_name = "sun" if key == LIGHT else ("moon" if key == DARK else "settings")
            button.setIcon(icon(icon_name, color, 16))
        effective = self._theme_manager.effective_theme
        self._palette_name.setText("ISAI Dark" if effective == DARK else "ISAI Light")
        for token, swatch in self._swatches.items():
            swatch.setStyleSheet(
                f"background-color: {getattr(colors, token)}; border: 1px solid {colors.border}; border-radius: 5px;"
            )
        self.reduced_motion_checkbox.blockSignals(True)
        self.reduced_motion_checkbox.setChecked(self._theme_manager.reduced_motion)
        self.reduced_motion_checkbox.blockSignals(False)
        self._sync_desktop_settings()

    @property
    def palette_name(self) -> str:
        return self._palette_name.text()
