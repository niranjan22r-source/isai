"""Collapsible sidebar navigation for ISAI."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QSize, Qt, Signal, QVariantAnimation
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from ui.icons import icon

EXPANDED_WIDTH = 232
COLLAPSED_WIDTH = 68

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("home", "Home", "home"),
    ("now_playing", "Now Playing", "note"),
    ("songs", "Songs", "songs"),
    ("albums", "Albums", "albums"),
    ("artists", "Artists", "artists"),
    ("playlists", "Playlists", "playlists"),
    ("favorites", "Favorites", "favorites"),
    ("recent", "Recently Played", "recent"),
    ("equalizer", "Equalizer", "equalizer"),
    ("settings", "Settings", "settings"),
)


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class NavigationItem(QPushButton):
    """A checkable sidebar entry that keeps its identity when collapsed."""

    def __init__(
        self,
        key: str,
        label: str,
        icon_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self.key = key
        self.label = label
        self.icon_name = icon_name
        self._colors: ThemeColors | None = None
        self._collapsed = False

        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(18, 18))
        self.setToolTip(label)
        self.setAccessibleName(label)
        self.setMinimumHeight(38)
        self.toggled.connect(self._update_icon)

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self._update_icon()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setText("" if collapsed else self.label)
        self.setToolTip(self.label)
        self.setProperty("collapsed", "true" if collapsed else "false")
        _repolish(self)
        self._update_icon()

    def _update_icon(self) -> None:
        if self._colors is None:
            return
        color = self._colors.accent if self.isChecked() else self._colors.text_muted
        self.setIcon(icon(self.icon_name, color, 18))


class Sidebar(QWidget):
    """Application navigation with an expanded and a compact mode."""

    navigation_requested = Signal(str)

    def __init__(
        self,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme_manager = theme_manager
        self._collapsed = False
        self._items: dict[str, NavigationItem] = {}

        self.setObjectName("sidebar")
        self.setFixedWidth(EXPANDED_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("sidebarHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 20, 16, 18)
        header_layout.setSpacing(10)

        self.logo_label = QLabel(header)
        self.logo_label.setObjectName("logoMark")
        self.logo_label.setFixedSize(36, 36)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        brand = QVBoxLayout()
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setSpacing(0)
        self.wordmark_label = QLabel("ISAI", header)
        self.wordmark_label.setObjectName("wordmark")
        wordmark_font = self.wordmark_label.font()
        wordmark_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        wordmark_font.setBold(True)
        self.wordmark_label.setFont(wordmark_font)
        brand.addWidget(self.wordmark_label)

        self.tagline_label = QLabel("Your music. Your space.", header)
        self.tagline_label.setObjectName("tagline")
        brand.addWidget(self.tagline_label)
        header_layout.addLayout(brand, 1)

        layout.addWidget(header)

        nav = QWidget(self)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(10, 12, 10, 10)
        nav_layout.setSpacing(4)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for key, label, icon_name in NAV_ITEMS[:-1]:
            item = NavigationItem(key, label, icon_name, nav)
            item.clicked.connect(
                lambda checked=False, page_key=key: self.navigation_requested.emit(
                    page_key
                )
            )
            self._group.addButton(item)
            self._items[key] = item
            nav_layout.addWidget(item)

        nav_layout.addStretch(1)

        settings_key, settings_label, settings_icon = NAV_ITEMS[-1]
        settings_item = NavigationItem(
            settings_key, settings_label, settings_icon, nav
        )
        settings_item.clicked.connect(
            lambda checked=False: self.navigation_requested.emit(settings_key)
        )
        self._group.addButton(settings_item)
        self._items[settings_key] = settings_item
        nav_layout.addWidget(settings_item)

        layout.addWidget(nav, 1)

        footer = QWidget(self)
        footer.setObjectName("sidebarFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(10, 10, 10, 10)

        self.toggle_button = QPushButton("Collapse", footer)
        self.toggle_button.setObjectName("sidebarToggle")
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setToolTip("Collapse sidebar")
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        footer_layout.addWidget(self.toggle_button)

        layout.addWidget(footer)

        self.refresh_theme(theme_manager.colors)

    @property
    def is_collapsed(self) -> bool:
        return self._collapsed

    def item(self, key: str) -> NavigationItem:
        return self._items[key]

    def set_current(self, key: str) -> None:
        item = self._items.get(key)
        if item is not None:
            item.setChecked(True)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        target = COLLAPSED_WIDTH if collapsed else EXPANDED_WIDTH
        start = self.width()

        self.wordmark_label.setVisible(not collapsed)
        self.tagline_label.setVisible(not collapsed)
        for item in self._items.values():
            item.set_collapsed(collapsed)

        self.toggle_button.setText("" if collapsed else "Collapse")
        self.toggle_button.setToolTip(
            "Expand sidebar" if collapsed else "Collapse sidebar"
        )
        self.toggle_button.setProperty(
            "collapsed", "true" if collapsed else "false"
        )
        _repolish(self.toggle_button)
        self._update_toggle_icon()

        reduce = False
        try:
            reduce = bool(self._theme_manager.reduced_motion)
        except Exception:
            reduce = False
        try:
            from PySide6.QtGui import QGuiApplication

            if QGuiApplication.platformName() == "offscreen":
                reduce = True
        except Exception:
            pass
        if reduce or start == target:
            self.setFixedWidth(target)
            return
        anim = getattr(self, "_width_anim", None)
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass
        anim = QVariantAnimation(self)
        anim.setStartValue(int(start))
        anim.setEndValue(int(target))
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.valueChanged.connect(lambda v: self.setFixedWidth(int(v)))
        anim.finished.connect(lambda: self.setFixedWidth(int(target)))
        self._width_anim = anim
        anim.start()

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.logo_label.setPixmap(
            icon("note", colors.accent, 20).pixmap(QSize(20, 20))
        )
        self._update_toggle_icon()
        for item in self._items.values():
            item.refresh_theme(colors)

    def _update_toggle_icon(self) -> None:
        colors = self._theme_manager.colors
        self.toggle_button.setIcon(
            icon(
                "chevron-right" if self._collapsed else "chevron-left",
                colors.text_muted,
                16,
            )
        )
