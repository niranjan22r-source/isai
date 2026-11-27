"""Search field with a theme-aware symbolic search icon."""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QWidget

from core.theme_manager import ThemeColors
from ui.icons import icon


class SearchField(QLineEdit):
    """A styled search input. Filtering is wired up in a later session."""

    def __init__(
        self,
        placeholder: str = "Search",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("searchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(180)
        self._search_action = self.addAction(
            icon("search", "#6a7382", 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._search_action.setIcon(icon("search", colors.text_muted, 16))
