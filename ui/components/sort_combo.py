"""Sorting combo box with a theme-aware symbolic chevron."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QComboBox, QWidget

from core.theme_manager import ThemeColors
from ui.icons import icon


class SortComboBox(QComboBox):
    """A QComboBox that paints its own chevron so it matches the theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sortCombo")
        self.setMinimumWidth(132)
        self._icon_color = "#6a7382"

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._icon_color = colors.text_muted
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        pixmap = icon("chevron-down", self._icon_color, 14).pixmap(QSize(14, 14))
        painter.drawPixmap(
            QRect(self.width() - 24, (self.height() - 14) // 2, 14, 14),
            pixmap,
        )
        painter.end()
