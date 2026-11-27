"""Responsive grid container for album and artist cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QWidget


class CardGrid(QWidget):
    """Lays cards out in as many columns as the available width allows."""

    def __init__(
        self,
        card_width: int = 168,
        spacing: int = 18,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._card_width = card_width
        self._spacing = spacing
        self._cards: list[QWidget] = []
        self._columns = 0

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def add_card(self, card: QWidget) -> None:
        if card not in self._cards:
            self._cards.append(card)
        card.setParent(self)
        self._columns = 0
        self._reflow()

    def clear(self) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._columns = 0

    def column_count(self) -> int:
        return self._columns or 1

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._reflow()

    def _reflow(self) -> None:
        if not self._cards:
            return
        columns = max(
            1, (max(self.width(), 1) + self._spacing) // (self._card_width + self._spacing)
        )
        if columns == self._columns:
            return
        self._columns = columns
        for index, card in enumerate(self._cards):
            self._grid.addWidget(
                card,
                index // columns,
                index % columns,
                Qt.AlignmentFlag.AlignTop,
            )


