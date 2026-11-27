"""Artist card used by the Artists page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from core.theme_manager import ThemeColors
from ui.icons import icon

AVATAR_SIZE = 120


class ArtistCard(QFrame):
    """A reusable artist tile with a circular placeholder avatar."""

    clicked = Signal(object)

    def __init__(
        self,
        name: str,
        subtitle: str = "",
        payload: object = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("artistCard")
        self.setFixedWidth(148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.payload = payload
        self._name = name
        self._subtitle = subtitle

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.avatar_label = QLabel(self)
        self.avatar_label.setObjectName("artistAvatar")
        self.avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.avatar_label, 0, Qt.AlignmentFlag.AlignHCenter)

        self.name_label = QLabel(self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(False)
        self.name_label.setToolTip(name)
        layout.addWidget(self.name_label)

        self.subtitle_label = QLabel(self)
        self.subtitle_label.setObjectName("cardSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_label.setWordWrap(False)
        self.subtitle_label.setToolTip(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)
        self._update_text()

    def _update_text(self) -> None:
        width = max(40, self.width() - 20)
        fm = self.name_label.fontMetrics()
        self.name_label.setText(
            fm.elidedText(self._name, Qt.TextElideMode.ElideRight, width)
        )
        sfm = self.subtitle_label.fontMetrics()
        self.subtitle_label.setText(
            sfm.elidedText(self._subtitle, Qt.TextElideMode.ElideRight, width)
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_text()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        super().mousePressEvent(event)

    def refresh_theme(self, colors: ThemeColors) -> None:
        self.avatar_label.setPixmap(
            icon("artists", colors.text_faint, 36).pixmap(QSize(36, 36))
        )
