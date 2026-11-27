"""Atmospheric queue panel backed entirely by the authoritative QueueManager."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from services.audio_engine import AudioEngine
from services.queue_manager import QueueItem
from ui.components.queue_row import QueueRow


class QueuePanel(QFrame):
    """Right-side queue panel with readable rows and stable ordering."""

    def __init__(
        self,
        theme_manager: ThemeManager,
        audio_engine: AudioEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("queuePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(330)
        self.setMaximumWidth(430)
        self._theme_manager = theme_manager
        self._colors = theme_manager.colors
        self._engine = audio_engine
        self._items: list[QueueItem] = []
        self._last_signature: tuple | None = None
        self._last_structure: tuple | None = None
        self._rows: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(1)
        self.title_label = QLabel("Queue", self)
        self.title_label.setObjectName("sectionTitle")
        title_col.addWidget(self.title_label)
        self.count_label = QLabel("", self)
        self.count_label.setObjectName("countLabel")
        title_col.addWidget(self.count_label)
        header.addLayout(title_col)
        header.addStretch(1)
        self.clear_btn = QPushButton("Clear", self)
        self.clear_btn.setObjectName("linkButton")
        self.clear_btn.clicked.connect(self._clear_queue)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.now_label = QLabel("NOW PLAYING", self)
        self.now_label.setObjectName("sectionHint")
        layout.addWidget(self.now_label)
        self.current_label = QLabel("Nothing playing", self)
        self.current_label.setObjectName("queueCurrentLabel")
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)

        self.up_next_label = QLabel("UP NEXT", self)
        self.up_next_label.setObjectName("sectionHint")
        layout.addWidget(self.up_next_label)

        self.list = QListWidget(self)
        self.list.setObjectName("queueList")
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Ordering is owned by QueueManager; drag is deliberately disabled so
        # the list can never drift from the model.
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.list.doubleClicked.connect(self._play_selected)
        self.list.setSpacing(1)
        layout.addWidget(self.list, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.play_btn = QPushButton("Play", self)
        self.play_btn.setObjectName("secondaryButton")
        self.play_btn.clicked.connect(self._play_selected)
        self.up_btn = QPushButton("Move up", self)
        self.up_btn.setObjectName("secondaryButton")
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))
        self.down_btn = QPushButton("Move down", self)
        self.down_btn.setObjectName("secondaryButton")
        self.down_btn.clicked.connect(lambda: self._move_selected(1))
        self.remove_btn = QPushButton("Remove", self)
        self.remove_btn.setObjectName("secondaryButton")
        self.remove_btn.clicked.connect(self._remove_selected)
        for button in (self.play_btn, self.up_btn, self.down_btn, self.remove_btn):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.empty_label = QLabel(
            "The queue is empty.\nPlay a song or add tracks to build one.",
            self,
        )
        self.empty_label.setObjectName("pageSubtitle")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        self._engine.queue_changed.connect(self.refresh_queue)
        self._engine.track_changed.connect(lambda _t: self.refresh_queue())
        self.refresh_theme(theme_manager.colors)
        self.refresh_queue()

    # --------------------------------------------------------------- rendering

    def refresh_queue(self) -> None:
        qm = self._engine.queue_manager
        items = list(qm.items)
        current_index = qm.current_index
        current = qm.current_item
        self._items = items

        if current is None:
            self.current_label.setText("Nothing playing")
        else:
            artist = current.artist or "Unknown artist"
            self.current_label.setText(f"{current.title} — {artist}")

        count = len(items)
        self.count_label.setText(f"{count} track{'s' if count != 1 else ''}")

        # Fast path: the queue contents and theme are unchanged, only the
        # current position moved. Rebuilding thousands of row widgets here
        # is what used to stall track changes, so update rows in place.
        structure = (
            tuple(i.queue_id for i in items),
            self._colors.bg,
            self._colors.surface_alt,
        )
        if (
            structure == self._last_structure
            and len(self._rows) == count
        ):
            self._apply_current_row(current_index)
            return

        self._last_structure = structure
        self._last_signature = (structure[0], current_index)

        selected_id = None
        selected_row = self.list.currentRow()
        if 0 <= selected_row < len(self._items):
            selected_id = self._items[selected_row].queue_id

        self.list.clear()
        self._rows = []
        for i, item in enumerate(items):
            lw = QListWidgetItem()
            lw.setData(Qt.ItemDataRole.UserRole, item.queue_id)
            lw.setToolTip(str(item.path))
            lw.setSizeHint(QSize(0, QueueRow.ROW_HEIGHT))
            self.list.addItem(lw)
            row = QueueRow(
                item,
                i,
                i == current_index,
                self._colors,
                parent=self.list,
            )
            self.list.setItemWidget(lw, row)
            self._rows.append(row)
            if item.queue_id == selected_id:
                self.list.setCurrentRow(i)

        has = count > 0
        self.list.setVisible(has)
        self.empty_label.setVisible(not has)
        self.up_next_label.setVisible(has)
        for button in (self.play_btn, self.up_btn, self.down_btn, self.remove_btn):
            button.setEnabled(has)
        self.clear_btn.setEnabled(has)

    def _apply_current_row(self, current_index: int) -> None:
        for i, row in enumerate(self._rows):
            try:
                row.set_current(i == current_index, i)
            except RuntimeError:
                # Underlying C++ widget already deleted; drop it.
                continue
            except Exception:
                pass

    # ---------------------------------------------------------------- actions

    def _selected_queue_id(self) -> int | None:
        row = self.list.currentRow()
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row].queue_id

    def _play_selected(self) -> None:
        qid = self._selected_queue_id()
        if qid is not None:
            self._engine.skip_to_queue_id(qid, autoplay=True)

    def _remove_selected(self) -> None:
        qid = self._selected_queue_id()
        if qid is None:
            return
        # AudioEngine listens to QueueManager.current_changed and loads/stops
        # as needed, so the panel never needs to touch engine internals.
        self._engine.queue_manager.remove_from_queue(qid)
        self.refresh_queue()

    def _clear_queue(self) -> None:
        self._engine.stop()
        self._engine.queue_manager.clear_queue()
        self.refresh_queue()

    def _move_selected(self, delta: int) -> None:
        row = self.list.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if not (0 <= new_row < len(self._items)):
            return
        if self._engine.queue_manager.move_queue_item(row, new_row):
            self.refresh_queue()
            self.list.setCurrentRow(new_row)

    # ------------------------------------------------------------------ theme

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self.refresh_queue()
