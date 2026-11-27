"""Section heading with an optional text action."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class SectionHeader(QWidget):
    """A small heading row used inside pages such as Home and Settings."""

    action_clicked = Signal()

    def __init__(
        self,
        title: str,
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("sectionTitle")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.action_button: QPushButton | None = None
        if action_text:
            self.action_button = QPushButton(action_text, self)
            self.action_button.setObjectName("linkButton")
            self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_button.clicked.connect(self.action_clicked)
            layout.addWidget(self.action_button)
