"""Consistent empty-state panel used across ISAI pages."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from core.theme_manager import ThemeColors
from ui.icons import icon


class EmptyState(QFrame):
    """A quiet, intentional placeholder for a page or section with no data."""

    def __init__(
        self,
        icon_name: str,
        title: str,
        description: str,
        compact: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._compact = compact

        self.setObjectName("emptyState")
        self.setProperty("compact", "true" if compact else "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24 if compact else 40, 24, 24 if compact else 40)
        layout.setSpacing(8 if compact else 12)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        size = 40 if compact else 56
        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("emptyIcon")
        self.icon_label.setProperty("compact", "true" if compact else "false")
        self.icon_label.setFixedSize(size, size)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("emptyTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.description_label = QLabel(description, self)
        self.description_label.setObjectName("emptyDescription")
        self.description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description_label.setWordWrap(True)
        self.description_label.setMaximumWidth(430)
        self._set_description_height(description)
        layout.addWidget(self.description_label, 0, Qt.AlignmentFlag.AlignHCenter)

    def _set_description_height(self, description: str) -> None:
        metrics = self.description_label.fontMetrics()
        wrapped = metrics.boundingRect(
            0,
            0,
            430,
            10000,
            Qt.TextFlag.TextWordWrap,
            description,
        )
        self.description_label.setMinimumHeight(wrapped.height() + 2)

    def set_message(self, title: str, description: str) -> None:
        self.title_label.setText(title)
        self.description_label.setText(description)
        self._set_description_height(description)

    def refresh_theme(self, colors: ThemeColors) -> None:
        icon_size = 18 if self._compact else 24
        self.icon_label.setPixmap(
            icon(self._icon_name, colors.text_faint, icon_size).pixmap(
                QSize(icon_size, icon_size)
            )
        )
