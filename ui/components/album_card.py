"""Album card used by the Albums page."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from core.theme_manager import ThemeColors
from ui.components.artwork import artwork_ready_connect, request_rounded_pixmap
from ui.icons import icon

ART_SIZE = 168


class AlbumCard(QFrame):
    """A reusable album tile with artwork, title, and subtitle."""

    clicked = Signal(object)  # emits self
    double_clicked = Signal(object)

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        artwork_path: str | None = None,
        payload: object = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("albumCard")
        self.setFixedWidth(ART_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.payload = payload
        self._artwork_path = artwork_path
        self._colors: ThemeColors | None = None
        self._title = title
        self._subtitle = subtitle
        self._art_key = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 10)
        layout.setSpacing(8)

        self.art_label = QLabel(self)
        self.art_label.setObjectName("albumArt")
        self.art_label.setFixedSize(ART_SIZE - 12, ART_SIZE - 12)
        self.art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.art_label)

        self.title_label = QLabel(self)
        self.title_label.setWordWrap(False)
        self.title_label.setToolTip(title)
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(self)
        self.subtitle_label.setObjectName("cardSubtitle")
        self.subtitle_label.setWordWrap(False)
        self.subtitle_label.setToolTip(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))
        layout.addWidget(self.subtitle_label)
        self._update_text()
        artwork_ready_connect(self._on_art_ready)

    def _update_text(self) -> None:
        width = max(40, self.width() - 16)
        fm = self.title_label.fontMetrics()
        self.title_label.setText(
            fm.elidedText(self._title, Qt.TextElideMode.ElideRight, width)
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

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self)
        super().mouseDoubleClickEvent(event)

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self._update_art()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

    def _update_art(self) -> None:
        if self._colors is None:
            return
        size = self.art_label.size().width()
        pixmap, key = request_rounded_pixmap(
            self._artwork_path,
            size,
            10,
            fallback_color=self._colors.surface_alt,
            fallback_icon="albums",
        )
        self._art_key = key
        if pixmap is not None:
            self.art_label.setPixmap(pixmap)
        else:
            self.art_label.setPixmap(
                icon("albums", self._colors.text_faint, 32).pixmap(QSize(32, 32))
            )

    def _on_art_ready(self, key, pixmap) -> None:
        if key != self._art_key or pixmap is None:
            return
        try:
            self.art_label.setPixmap(pixmap)
        except Exception:
            pass
