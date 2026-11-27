"""Dialog for creating or renaming playlists."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PlaylistDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "Create Playlist",
        name: str = "",
        description: str = "",
        confirm_label: str = "Create",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("Playlist name")
        self.name_edit.setText(name)
        self.name_edit.setMaxLength(80)
        form.addRow("Name", self.name_edit)

        self.description_edit = QTextEdit(self)
        self.description_edit.setPlaceholderText("Optional description")
        self.description_edit.setPlainText(description)
        self.description_edit.setMaximumHeight(90)
        form.addRow("Description", self.description_edit)

        layout.addLayout(form)

        self.buttons = QDialogButtonBox(self)
        self.create_button = self.buttons.addButton(confirm_label, QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.create_button.clicked.connect(self._on_accept)
        self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.buttons)

        self.name_edit.textChanged.connect(self._sync_state)
        self._sync_state()

    def _sync_state(self) -> None:
        self.create_button.setEnabled(bool(self.name_edit.text().strip()))

    def _on_accept(self) -> None:
        if self.name_edit.text().strip():
            self.accept()

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.description_edit.toPlainText().strip()
