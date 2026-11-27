"""Scrollable page scaffold shared by all ISAI pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components.page_header import PageHeader


class BasePage(QScrollArea):
    """A scrollable page with a consistent header and content column."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        action: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        content = QWidget(self)
        content.setObjectName("pageContent")
        self.content = content

        outer = QVBoxLayout(content)
        outer.setContentsMargins(32, 28, 32, 32)
        outer.setSpacing(20)

        self.header = PageHeader(title, subtitle, action, content)
        outer.addWidget(self.header)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(20)
        outer.addLayout(self.body, 1)

        self.setWidget(content)

    def set_ambient_gradient(self, gradient: str) -> None:
        """Apply a page-level artwork wash without disturbing child widgets."""
        self.content.setStyleSheet(
            "QWidget#pageContent { background: %s; }" % gradient
        )

    def clear_ambient_gradient(self) -> None:
        self.content.setStyleSheet("")
