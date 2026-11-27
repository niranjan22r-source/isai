"""Page heading used at the top of every page."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    """A consistent page title, optional subtitle, and optional action."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        action: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(16)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("pageTitle")
        self.title_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle, self)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        text_layout.addWidget(self.subtitle_label)

        layout.addLayout(text_layout, 1)

        self.action = action
        if action is not None:
            layout.addWidget(action, 0)
