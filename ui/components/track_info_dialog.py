"""Read-only track metadata dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.library_database import TrackRecord
from ui.player_bar import format_time


def _fmt(value: object, fallback: str = "—") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        value = value.strip()
        return value if value else fallback
    return str(value)


def _fmt_size(size_bytes: int) -> str:
    size = max(0, int(size_bytes))
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


class TrackInfoDialog(QDialog):
    def __init__(self, track: TrackRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Track Information")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.resize(560, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget(scroll)
        form = QFormLayout(container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        rows = [
            ("Title", _fmt(track.title)),
            ("Artist", _fmt(track.artist)),
            ("Album", _fmt(track.album)),
            ("Album artist", _fmt(track.album_artist)),
            ("Track number", _fmt(track.track_number)),
            ("Disc number", _fmt(track.disc_number)),
            ("Genre", _fmt(track.genre)),
            ("Year", _fmt(track.year)),
            ("Duration", format_time(track.duration) if track.duration else "—"),
            ("Format", _fmt(track.format.upper() if track.format else "")),
            ("Bitrate", f"{track.bitrate // 1000} kbps" if track.bitrate else "—"),
            ("File size", _fmt_size(track.file_size)),
            ("File path", _fmt(track.file_path)),
        ]
        for label, value in rows:
            value_label = QLabel(value, container)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value_label.setWordWrap(True)
            value_label.setToolTip(value)
            form.addRow(f"{label}:", value_label)

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
