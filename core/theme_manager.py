"""Centralized theme handling for ISAI.

The theme manager owns the palette tokens, the application style sheet, the
light/dark switch, and persistence of the user's choice via QSettings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from string import Template

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

DARK = "dark"
LIGHT = "light"
SYSTEM = "system"
THEME_SETTINGS_KEY = "appearance/theme"
REDUCED_MOTION_KEY = "appearance/reduced_motion"


@dataclass(frozen=True)
class ThemeColors:
    """Named color tokens used by both the style sheet and the icons.

    The names are kept stable from earlier sessions; values evolve with the
    visual language while preserving every existing token used by pages and
    tests.
    """

    bg: str
    sidebar_bg: str
    surface: str
    surface_alt: str
    card: str
    border: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    accent_subtle: str
    hover: str
    input_bg: str
    player_bg: str
    track: str
    danger: str
    bg_soft: str
    border_strong: str
    ambient: str
    ambient_soft: str


THEMES: dict[str, ThemeColors] = {
    DARK: ThemeColors(
        # "Noir Studio" — deep charcoal stage, warm graphite surfaces, amber accent.
        bg="#0c0d10",
        sidebar_bg="#111318",
        surface="#181b21",
        surface_alt="#20242c",
        card="#15181e",
        border="#262b34",
        text="#f4f1ec",
        text_muted="#a8a095",
        text_faint="#726c64",
        accent="#d6a156",
        accent_hover="#e0b06a",
        accent_pressed="#c08c42",
        accent_text="#161006",
        accent_subtle="#2a2418",
        hover="#1e222a",
        input_bg="#13161b",
        player_bg="#0a0b0e",
        track="#333944",
        danger="#ef7a6a",
        bg_soft="#12151a",
        border_strong="#363d48",
        ambient="#2a2115",
        ambient_soft="#1c1914",
    ),
    LIGHT: ThemeColors(
        # "Ivory Studio" — warm paper neutrals, clear hierarchy, amber accent.
        bg="#f5f3ef",
        sidebar_bg="#ebe8e2",
        surface="#fffdf9",
        surface_alt="#f0ece5",
        card="#fffdf9",
        border="#ddd8cf",
        text="#1f1b16",
        text_muted="#635d55",
        text_faint="#8a847b",
        accent="#b07a2a",
        accent_hover="#c48932",
        accent_pressed="#966621",
        accent_text="#fffaf2",
        accent_subtle="#f3e6d0",
        hover="#e8e3da",
        input_bg="#fffdf9",
        player_bg="#faf8f4",
        track="#d2ccc1",
        danger="#d4584a",
        bg_soft="#fbf9f5",
        border_strong="#c7c0b4",
        ambient="#efe2cd",
        ambient_soft="#f7f1e6",
    ),
}


_STYLESHEET = Template(
    """
/* ============================================================ ISAI — shell */

QMainWindow, QWidget#appRoot {
    background-color: $bg;
}

QWidget {
    color: $text;
    font-size: 13px;
}

QWidget#contentArea, QStackedWidget#pageStack {
    background-color: $bg;
}

QScrollArea#pageScroll,
QScrollArea#pageScroll > QWidget > QWidget,
QWidget#pageContent {
    background-color: transparent;
    border: none;
}

/* ------------------------------------------------------------- navigation */

QWidget#sidebar {
    background-color: $sidebar_bg;
    border-right: 1px solid $border;
}

QWidget#sidebarHeader {
    border-bottom: 1px solid $border;
}

QWidget#sidebarFooter {
    border-top: 1px solid $border;
}

QLabel#wordmark {
    color: $text;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 2px;
}

QLabel#tagline {
    color: $text_faint;
    font-size: 10px;
    letter-spacing: 0.4px;
}

QLabel#logoMark {
    background-color: $accent_subtle;
    border: 1px solid $border;
    border-radius: 11px;
}

QPushButton#navButton {
    text-align: left;
    padding: 9px 12px;
    border: none;
    border-radius: 10px;
    color: $text_muted;
    font-size: 13px;
    font-weight: 500;
}

QPushButton#navButton:hover {
    background-color: $hover;
    color: $text;
}

QPushButton#navButton:checked {
    background-color: $accent_subtle;
    color: $accent;
    font-weight: 600;
}

QPushButton#navButton[collapsed="true"] {
    text-align: center;
    padding: 9px 0;
}

QPushButton#sidebarToggle {
    color: $text_faint;
    text-align: left;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 12px;
}

QPushButton#sidebarToggle:hover {
    background-color: $hover;
    color: $text;
}

QPushButton#sidebarToggle[collapsed="true"] {
    text-align: center;
    padding: 8px 0;
}

/* -------------------------------------------------------------- typography */

QLabel#pageTitle {
    font-size: 30px;
    font-weight: 600;
    color: $text;
    letter-spacing: -0.2px;
}

QLabel#pageSubtitle {
    color: $text_muted;
    font-size: 13px;
}

QLabel#sectionTitle {
    font-size: 17px;
    font-weight: 600;
    color: $text;
}

QLabel#sectionHint {
    color: $text_faint;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
}

QLabel#countLabel {
    color: $text_faint;
    font-size: 12px;
}

QLabel#emptyTitle {
    font-size: 16px;
    font-weight: 600;
    color: $text;
}

QLabel#emptyDescription {
    color: $text_muted;
    font-size: 12px;
}

QLabel#emptyIcon {
    background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: 28px;
}

QLabel#emptyIcon[compact="true"] {
    border-radius: 20px;
}

QLabel#trackTitle {
    font-size: 13px;
    font-weight: 600;
}

QLabel#trackTitle[inactive="true"] {
    color: $text_muted;
}

QLabel#trackArtist {
    color: $text_faint;
    font-size: 11px;
}

QLabel#trackArtist[error="true"] {
    color: $danger;
}

QLabel#timeLabel {
    color: $text_faint;
    font-size: 11px;
}

QLabel#cardSubtitle, QLabel#settingsValue {
    color: $text_muted;
    font-size: 12px;
}

/* ---------------------------------------------------------------- buttons */

QPushButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    color: $text;
    padding: 7px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: $hover;
}

QPushButton:pressed {
    background-color: $surface_alt;
}

QPushButton:focus {
    outline: none;
    border: 1px solid $accent;
}

QPushButton:disabled {
    color: $text_faint;
}

QPushButton#primaryButton {
    background-color: $accent;
    color: $accent_text;
    font-weight: 600;
    padding: 9px 18px;
    border: none;
    border-radius: 10px;
}

QPushButton#primaryButton:hover {
    background-color: $accent_hover;
}

QPushButton#primaryButton:pressed {
    background-color: $accent_pressed;
}

QPushButton#primaryButton:disabled {
    background-color: $surface_alt;
    color: $text_faint;
}

QPushButton#secondaryButton {
    background-color: transparent;
    border: 1px solid $border_strong;
    color: $text;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 10px;
}

QPushButton#secondaryButton:hover {
    background-color: $hover;
    border-color: $accent;
    color: $text;
}

QPushButton#linkButton {
    color: $accent;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 8px;
}

QPushButton#linkButton:hover {
    background-color: $accent_subtle;
}

QPushButton#iconButton {
    padding: 6px;
    min-width: 30px;
    min-height: 30px;
    border-radius: 8px;
}

QPushButton#themeOption {
    background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: 8px;
    color: $text_muted;
    padding: 7px 14px;
}

QPushButton#themeOption:hover {
    background-color: $hover;
    color: $text;
}

QPushButton#themeOption:checked {
    background-color: $accent;
    border-color: $accent;
    color: $accent_text;
    font-weight: 600;
}

QPushButton#sortDirButton {
    background-color: $input_bg;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 10px;
    color: $text_muted;
}

QPushButton#sortDirButton:hover {
    background-color: $hover;
    color: $text;
    border-color: $border_strong;
}

QPushButton#scanCancelButton {
    padding: 4px 10px;
    font-size: 12px;
}

/* --------------------------------------------------------------- inputs */

QLineEdit#searchField {
    background-color: $input_bg;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 22px;
    selection-background-color: $accent;
    selection-color: $accent_text;
}

QLineEdit#searchField:focus {
    border-color: $accent;
    background-color: $surface;
}

QComboBox {
    background-color: $input_bg;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 26px;
    color: $text;
}

QComboBox:focus {
    border-color: $accent;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox QAbstractItemView {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    color: $text;
    selection-background-color: $accent_subtle;
    selection-color: $text;
    outline: none;
}

QCheckBox {
    color: $text_muted;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid $border_strong;
    background-color: $input_bg;
}

QCheckBox::indicator:checked {
    background-color: $accent;
    border-color: $accent;
}

/* --------------------------------------------------------------- surfaces */

QFrame#settingsCard {
    background-color: $card;
    border: 1px solid $border;
    border-radius: 14px;
}

QFrame#settingsRow {
    border-bottom: 1px solid $border;
}

QFrame#settingsRow[last="true"] {
    border-bottom: none;
}

QLabel#settingsTitle {
    font-size: 13px;
    font-weight: 600;
}

QLabel#settingsDescription {
    color: $text_muted;
    font-size: 12px;
}

QFrame#emptyState {
    background-color: transparent;
    border: 1px dashed $border_strong;
    border-radius: 14px;
}

QFrame#emptyState[compact="true"] {
    background-color: transparent;
    border: 1px dashed $border;
    border-radius: 12px;
}

QFrame#toolbar {
    background-color: transparent;
    border: none;
}

QFrame#heroPanel {
    background-color: $bg_soft;
    border: 1px solid $border;
    border-radius: 20px;
}

QLabel#heroEyebrow {
    color: $accent;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}

QLabel#heroTitle {
    color: $text;
    font-size: 34px;
    font-weight: 600;
}

QLabel#heroSubtitle {
    color: $text_muted;
    font-size: 14px;
}

QLabel#heroStatValue {
    color: $text;
    font-size: 20px;
    font-weight: 600;
}

QLabel#heroStatLabel {
    color: $text_faint;
    font-size: 11px;
    letter-spacing: 0.3px;
}

/* ------------------------------------------------------------- media cards */

QFrame#albumCard, QFrame#artistCard {
    background-color: transparent;
    border: none;
    border-radius: 12px;
}

QFrame#albumCard:hover, QFrame#artistCard:hover {
    background-color: $hover;
}

QLabel#albumArt {
    background-color: $surface_alt;
    border-radius: 10px;
}

QLabel#artistAvatar {
    background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: 60px;
}

QLabel#albumArtPlaceholder {
    background-color: $surface_alt;
    border-radius: 10px;
}

QFrame#trackTile {
    background-color: transparent;
    border: none;
    border-radius: 12px;
}

QFrame#trackTile:hover {
    background-color: $hover;
}

QLabel#trackTileArt {
    background-color: $surface_alt;
    border-radius: 10px;
}

QLabel#trackTileTitle {
    color: $text;
    font-size: 13px;
    font-weight: 600;
}

QLabel#trackTileArtist {
    color: $text_faint;
    font-size: 11px;
}

QScrollArea#trackShelf {
    background: transparent;
    border: none;
}

QScrollArea#trackShelf > QWidget > QWidget {
    background: transparent;
}

/* --------------------------------------------------------------- player bar */

QWidget#playerBar {
    background-color: $player_bg;
    border-top: 1px solid $border;
}

QWidget#playerProgressRow {
    background: transparent;
}

QLabel#playerArtwork {
    background-color: $surface_alt;
    border: 1px solid $border;
    border-radius: 10px;
}

QLabel#playerTrackTitle {
    color: $text;
    font-size: 13px;
    font-weight: 600;
}

QLabel#playerTrackTitle[inactive="true"] {
    color: $text_muted;
}

QLabel#playerTrackArtist {
    color: $text_faint;
    font-size: 11px;
}

QLabel#playerTrackArtist[error="true"] {
    color: $danger;
}

QLabel#playerTime {
    color: $text_faint;
    font-size: 11px;
}

QPushButton#playerButton {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 5px;
    min-width: 32px;
    min-height: 32px;
}

QPushButton#playerButton:hover {
    background-color: $hover;
}

QPushButton#playButton {
    background-color: $accent;
    border: none;
    border-radius: 22px;
    padding: 0;
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
}

QPushButton#playButton:hover {
    background-color: $accent_hover;
}

QPushButton#playButton:pressed {
    background-color: $accent_pressed;
}

QPushButton#playButton:disabled {
    background-color: $surface_alt;
}

/* ---------------------------------------------------------------- sliders */

QSlider::groove:horizontal {
    height: 4px;
    background-color: $track;
    border-radius: 2px;
}

QSlider::sub-page:horizontal {
    background-color: $accent;
    border-radius: 2px;
}

QSlider::sub-page:horizontal:disabled {
    background-color: $track;
}

QSlider::handle:horizontal {
    background-color: $text;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}

QSlider::handle:horizontal:hover {
    background-color: $accent;
}

QSlider::handle:horizontal:disabled {
    background-color: $text_faint;
}

/* ----------------------------------------------------------------- queue */

QFrame#queuePanel {
    background-color: $surface;
    border-left: 1px solid $border;
}

QLabel#queueCurrentLabel {
    color: $text;
    font-size: 14px;
    font-weight: 600;
    padding: 2px 0;
}

QListWidget#queueList {
    background-color: transparent;
    border: none;
    padding: 2px;
    outline: none;
}

QListWidget#queueList::item {
    padding: 0;
    border-radius: 10px;
}

QListWidget#queueList::item:selected {
    background-color: $accent_subtle;
}

QListWidget#queueList::item:hover {
    background-color: $hover;
}

QLabel#queueRowNumber {
    color: $text_faint;
    font-size: 11px;
}

QLabel#queueRowTitle {
    color: $text;
    font-size: 13px;
    font-weight: 600;
}

QLabel#queueRowArtist {
    color: $text_faint;
    font-size: 11px;
}

QLabel#queueRowDuration {
    color: $text_faint;
    font-size: 11px;
}

QLabel#queueRowArt {
    background-color: $surface_alt;
    border-radius: 8px;
}

/* ------------------------------------------------------------- now playing */

QFrame#nowPlayingCanvas {
    background-color: transparent;
    border: none;
}

QLabel#nowPlayingArtwork {
    background-color: transparent;
    border: none;
    border-radius: 24px;
}

QLabel#nowPlayingEyebrow {
    color: $accent;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}

QLabel#nowPlayingTitle {
    color: $text;
    font-size: 32px;
    font-weight: 600;
}

QLabel#nowPlayingArtist {
    color: $text_muted;
    font-size: 16px;
}

QLabel#nowPlayingAlbum {
    color: $text_faint;
    font-size: 12px;
}

QPushButton#nowPlayingPlay {
    background-color: $accent;
    border: none;
    border-radius: 27px;
    min-width: 54px;
    max-width: 54px;
    min-height: 54px;
    max-height: 54px;
}

QPushButton#nowPlayingPlay:hover {
    background-color: $accent_hover;
}

QPushButton#nowPlayingPlay:pressed {
    background-color: $accent_pressed;
}

QListWidget#lyricsList {
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px;
}

QListWidget#lyricsList::item {
    padding: 8px 10px;
    border-radius: 8px;
}

QListWidget#lyricsList::item:selected {
    background-color: $accent_subtle;
    color: $text;
}

QFrame#lyricsPanel {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 14px;
}

/* ------------------------------------------------------------ mini player */

QWidget#miniPlayer {
    background-color: $bg_soft;
    border: 1px solid $border;
    border-radius: 16px;
}

QLabel#miniTitle {
    color: $text;
    font-size: 14px;
    font-weight: 600;
}

QLabel#miniArtist {
    color: $text_faint;
    font-size: 11px;
}

/* ------------------------------------------------------------ lists/tables */

QTableWidget#songsTable, QTableWidget#recentTable {
    background-color: transparent;
    border: none;
    gridline-color: transparent;
    outline: none;
    selection-background-color: $accent_subtle;
    selection-color: $text;
}

QTableWidget#songsTable::item, QTableWidget#recentTable::item {
    padding: 8px 10px;
    border-bottom: 1px solid $border;
}

QTableWidget#songsTable::item:selected, QTableWidget#recentTable::item:selected {
    background-color: $accent_subtle;
    color: $text;
}

QHeaderView::section {
    background-color: transparent;
    color: $text_faint;
    border: none;
    border-bottom: 1px solid $border;
    padding: 9px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.2px;
}

QListWidget#homeTrackList {
    background-color: transparent;
    border: none;
    padding: 2px;
    outline: none;
}

QListWidget#homeTrackList::item {
    padding: 9px 10px;
    border-radius: 8px;
    color: $text;
}

QListWidget#homeTrackList::item:selected,
QListWidget#homeTrackList::item:hover {
    background-color: $hover;
}

/* --------------------------------------------------------------- overlays */

QMenu {
    background-color: $surface;
    border: 1px solid $border;
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    padding: 8px 22px 8px 12px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: $accent_subtle;
    color: $text;
}

QMenu::separator {
    height: 1px;
    background: $border;
    margin: 5px 8px;
}

QToolTip {
    background-color: $surface;
    color: $text;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 9px;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}

QScrollBar::handle:vertical {
    background-color: $track;
    min-height: 34px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background-color: $text_faint;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}

QScrollBar::handle:horizontal {
    background-color: $track;
    min-width: 34px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background-color: $text_faint;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

QWidget#scanStatus {
    background-color: $surface;
    border-top: 1px solid $border;
}

QLabel#scanLabel {
    color: $text_muted;
    font-size: 12px;
}

QProgressBar#scanProgress {
    background-color: $track;
    border: none;
    border-radius: 3px;
    min-height: 6px;
    max-height: 6px;
}

QProgressBar#scanProgress::chunk {
    background-color: $accent;
    border-radius: 3px;
}

QDialog {
    background-color: $bg;
}

QDialog QLineEdit {
    background-color: $input_bg;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: $accent;
    selection-color: $accent_text;
}

QDialog QLineEdit:focus {
    border-color: $accent;
}
"""
)


def default_settings() -> QSettings:
    """Return the lightweight, user-scoped settings store used by ISAI."""
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "ISAI",
        "ISAI",
    )


class ThemeManager(QObject):
    """Owns the active theme, applies it, and persists the user's choice."""

    theme_changed = Signal(str)
    reduced_motion_changed = Signal(bool)

    def __init__(
        self,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings if settings is not None else default_settings()
        stored = str(self._settings.value(THEME_SETTINGS_KEY, DARK)).lower()
        self._theme = stored if stored in (DARK, LIGHT, SYSTEM) else DARK
        rm = self._settings.value(REDUCED_MOTION_KEY, False)
        self._reduced_motion = (
            str(rm).lower() in ("1", "true", "yes") if isinstance(rm, str) else bool(rm)
        )
        self._system_connected = False
        self._connect_system_signal()

    @property
    def theme(self) -> str:
        """Selected preference: dark, light, or system."""
        return self._theme

    @property
    def effective_theme(self) -> str:
        if self._theme == SYSTEM:
            return self._detect_system_theme()
        return self._theme

    @property
    def colors(self) -> ThemeColors:
        return THEMES[self.effective_theme]

    @property
    def reduced_motion(self) -> bool:
        return self._reduced_motion

    def set_reduced_motion(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._reduced_motion:
            return
        self._reduced_motion = enabled
        self._settings.setValue(REDUCED_MOTION_KEY, enabled)
        self._settings.sync()
        self.reduced_motion_changed.emit(enabled)

    def supports_system_theme(self) -> bool:
        try:
            app = QApplication.instance()
            if app is None:
                return False
            hints = app.styleHints()
            return hasattr(hints, "colorScheme")
        except Exception:
            return False

    def _detect_system_theme(self) -> str:
        try:
            app = QApplication.instance()
            if app is None:
                return DARK
            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                scheme = hints.colorScheme()
                if scheme == Qt.ColorScheme.Light:
                    return LIGHT
                if scheme == Qt.ColorScheme.Dark:
                    return DARK
        except Exception:
            pass
        return DARK

    def _connect_system_signal(self) -> None:
        if self._system_connected:
            return
        try:
            app = QApplication.instance()
            if app is None:
                return
            hints = app.styleHints()
            if hasattr(hints, "colorSchemeChanged"):
                hints.colorSchemeChanged.connect(self._on_system_scheme_changed)
                self._system_connected = True
        except Exception:
            pass

    def _on_system_scheme_changed(self, *_args) -> None:
        if self._theme != SYSTEM:
            return
        app = QApplication.instance()
        if app is not None:
            self.apply(app)
        self.theme_changed.emit(self._theme)

    def set_theme(self, theme: str) -> None:
        normalized = str(theme).lower()
        allowed = (DARK, LIGHT, SYSTEM)
        if normalized not in allowed:
            raise ValueError(f"Unknown theme: {theme!r}")
        if normalized == SYSTEM and not self.supports_system_theme():
            # Fallback: keep setting but effective theme will be dark; caller/UI should explain.
            pass
        if normalized == self._theme:
            return
        self._theme = normalized
        self._settings.setValue(THEME_SETTINGS_KEY, normalized)
        self._settings.sync()
        self._connect_system_signal()
        app = QApplication.instance()
        if app is not None:
            self.apply(app)
        self.theme_changed.emit(normalized)

    def apply(self, app: QApplication | None = None) -> None:
        """Apply the active palette and style sheet to the application."""
        app = app if app is not None else QApplication.instance()
        if app is None:
            return
        self._connect_system_signal()
        app.setPalette(self.build_palette())
        app.setStyleSheet(self.stylesheet())

    def stylesheet(self) -> str:
        return _STYLESHEET.substitute(asdict(self.colors))

    def build_palette(self) -> QPalette:
        colors = self.colors
        palette = QPalette()
        role = QPalette.ColorRole
        group = QPalette.ColorGroup
        palette.setColor(role.Window, QColor(colors.bg))
        palette.setColor(role.WindowText, QColor(colors.text))
        palette.setColor(role.Base, QColor(colors.input_bg))
        palette.setColor(role.AlternateBase, QColor(colors.surface_alt))
        palette.setColor(role.Text, QColor(colors.text))
        palette.setColor(role.Button, QColor(colors.surface))
        palette.setColor(role.ButtonText, QColor(colors.text))
        palette.setColor(role.Highlight, QColor(colors.accent))
        palette.setColor(role.HighlightedText, QColor(colors.accent_text))
        palette.setColor(role.PlaceholderText, QColor(colors.text_faint))
        palette.setColor(role.ToolTipBase, QColor(colors.surface))
        palette.setColor(role.ToolTipText, QColor(colors.text))
        palette.setColor(group.Disabled, role.WindowText, QColor(colors.text_faint))
        palette.setColor(group.Disabled, role.Text, QColor(colors.text_faint))
        palette.setColor(group.Disabled, role.ButtonText, QColor(colors.text_faint))
        return palette
