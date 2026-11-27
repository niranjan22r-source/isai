"""Playback queue manager for ISAI.

The queue manager owns queue order, shuffle/repeat state, and current item
selection. AudioEngine remains responsible for actual audio playback.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, Signal

REPEAT_OFF = "off"
REPEAT_ALL = "all"
REPEAT_ONE = "one"
REPEAT_MODES = (REPEAT_OFF, REPEAT_ALL, REPEAT_ONE)


@dataclass
class QueueItem:
    queue_id: int
    path: Path
    track_id: int | None = None
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: int = 0
    artwork_path: str | None = None


class QueueManager(QObject):
    queue_changed = Signal()
    current_changed = Signal(object)  # QueueItem | None
    shuffle_changed = Signal(bool)
    repeat_changed = Signal(str)

    def __init__(self, parent: QObject | None = None, rng: random.Random | None = None) -> None:
        super().__init__(parent)
        self._rng = rng or random.Random()
        self._items: list[QueueItem] = []
        self._current_index: int = -1
        self._shuffle = False
        self._repeat = REPEAT_OFF
        self._next_queue_id = 1
        # original order of queue_ids for shuffle restore
        self._original_order: list[int] = []

    # ------------------------------------------------------------------ state

    @property
    def items(self) -> tuple[QueueItem, ...]:
        return tuple(self._items)

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current_item(self) -> QueueItem | None:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index]
        return None

    @property
    def shuffle(self) -> bool:
        return self._shuffle

    @property
    def repeat_mode(self) -> str:
        return self._repeat

    def has_tracks(self) -> bool:
        return bool(self._items)

    def upcoming_items(self) -> list[QueueItem]:
        if self._current_index < 0:
            return list(self._items)
        return list(self._items[self._current_index + 1 :])

    # ----------------------------------------------------------------- build

    def _make_item(self, track) -> QueueItem | None:
        # Accept QueueItem, TrackRecord-like, dict, or path-like
        if isinstance(track, QueueItem):
            return QueueItem(
                queue_id=self._next_queue_id,
                path=Path(track.path),
                track_id=track.track_id,
                title=track.title,
                artist=track.artist,
                album=track.album,
                duration=track.duration,
                artwork_path=track.artwork_path,
            )
        if isinstance(track, (str, Path)):
            path = Path(track)
            item = QueueItem(queue_id=self._next_queue_id, path=path, title=path.stem)
            self._next_queue_id += 1
            return item
        # TrackRecord-like object
        path = getattr(track, "file_path", None) or getattr(track, "path", None)
        if path is None and isinstance(track, dict):
            path = track.get("file_path") or track.get("path")
        if path is None:
            return None
        item = QueueItem(
            queue_id=self._next_queue_id,
            path=Path(path),
            track_id=getattr(track, "id", None) if not isinstance(track, dict) else track.get("id") or track.get("track_id"),
            title=getattr(track, "title", "") if not isinstance(track, dict) else str(track.get("title", "")),
            artist=getattr(track, "artist", "") if not isinstance(track, dict) else str(track.get("artist", "")),
            album=getattr(track, "album", "") if not isinstance(track, dict) else str(track.get("album", "")),
            duration=int(getattr(track, "duration", 0) if not isinstance(track, dict) else track.get("duration", 0) or 0),
            artwork_path=getattr(track, "artwork_path", None) if not isinstance(track, dict) else track.get("artwork_path"),
        )
        if not item.title:
            item.title = item.path.stem
        self._next_queue_id += 1
        return item

    def set_queue(self, tracks: Iterable, start_index: int = 0, autoplay: bool = False) -> QueueItem | None:
        items = []
        for t in tracks:
            item = self._make_item(t)
            if item is not None:
                items.append(item)
        self._items = items
        self._original_order = [i.queue_id for i in self._items]
        self._current_index = start_index if 0 <= start_index < len(self._items) else (-1 if not self._items else 0)
        if self._shuffle and len(self._items) > 1:
            self._apply_shuffle(keep_current=True)
        self.queue_changed.emit()
        self.current_changed.emit(self.current_item)
        return self.current_item

    def restore(self, tracks: Iterable, current_index: int = -1, shuffle: bool = False, repeat: str = REPEAT_OFF) -> QueueItem | None:
        """Restore persisted queue without reshuffling the saved order."""
        items = []
        for t in tracks:
            item = self._make_item(t)
            if item is not None:
                items.append(item)
        self._items = items
        self._original_order = [i.queue_id for i in self._items]
        self._current_index = current_index if 0 <= current_index < len(self._items) else (-1 if not self._items else 0)
        self._shuffle = bool(shuffle)
        self._repeat = repeat if repeat in REPEAT_MODES else REPEAT_OFF
        self.shuffle_changed.emit(self._shuffle)
        self.repeat_changed.emit(self._repeat)
        self.queue_changed.emit()
        self.current_changed.emit(self.current_item)
        return self.current_item

    def add_to_queue(self, track) -> QueueItem | None:
        return self.add_many_to_queue([track])[0] if track is not None else None

    def add_many_to_queue(self, tracks: Iterable) -> list[QueueItem]:
        added: list[QueueItem] = []
        for t in tracks:
            item = self._make_item(t)
            if item is None:
                continue
            self._items.append(item)
            self._original_order.append(item.queue_id)
            added.append(item)
        if added:
            if self._current_index < 0 and self._items:
                self._current_index = 0
                self.current_changed.emit(self.current_item)
            self.queue_changed.emit()
        return added

    def play_next(self, tracks: Iterable) -> list[QueueItem]:
        new_items = []
        for t in tracks if not isinstance(tracks, (str, Path)) and hasattr(tracks, '__iter__') and not hasattr(tracks, 'file_path') else [tracks]:
            item = self._make_item(t)
            if item is not None:
                new_items.append(item)
        if not new_items:
            return []
        insert_at = self._current_index + 1 if self._current_index >= 0 else 0
        self._items[insert_at:insert_at] = new_items
        # Insert into original order after current item's original position
        current = self.current_item
        if current and current.queue_id in self._original_order:
            pos = self._original_order.index(current.queue_id) + 1
            for i, item in enumerate(new_items):
                self._original_order.insert(pos + i, item.queue_id)
        else:
            self._original_order.extend([i.queue_id for i in new_items])
        if self._current_index < 0 and self._items:
            self._current_index = 0
            self.current_changed.emit(self.current_item)
        self.queue_changed.emit()
        return new_items

    # --------------------------------------------------------------- actions

    def remove_from_queue(self, queue_id: int) -> bool:
        idx = self._index_by_queue_id(queue_id)
        if idx < 0:
            return False
        removed_current = idx == self._current_index
        del self._items[idx]
        try:
            self._original_order.remove(queue_id)
        except ValueError:
            pass
        if not self._items:
            self._current_index = -1
            self.queue_changed.emit()
            self.current_changed.emit(None)
            return True
        if idx < self._current_index:
            self._current_index -= 1
        elif removed_current:
            # keep same index as next item; if at end, clamp
            if self._current_index >= len(self._items):
                self._current_index = len(self._items) - 1
            self.queue_changed.emit()
            self.current_changed.emit(self.current_item)
            return True
        self.queue_changed.emit()
        return True

    def move_queue_item(self, old_index: int, new_index: int) -> bool:
        if not (0 <= old_index < len(self._items) and 0 <= new_index < len(self._items)):
            return False
        if old_index == new_index:
            return False
        item = self._items.pop(old_index)
        self._items.insert(new_index, item)
        cur = self._current_index
        if old_index == cur:
            self._current_index = new_index
        elif old_index < cur <= new_index:
            self._current_index -= 1
        elif new_index <= cur < old_index:
            self._current_index += 1
        # A manual reorder while unshuffled becomes the new intended base order.
        # While shuffled, the shuffled order is only a view of the queue: keep
        # the original order untouched so disabling shuffle restores it.
        if not self._shuffle:
            self._sync_original_order_to_current()
        self.queue_changed.emit()
        return True

    def clear_queue(self) -> None:
        self._items.clear()
        self._original_order.clear()
        self._current_index = -1
        self.queue_changed.emit()
        self.current_changed.emit(None)

    def skip_to_queue_item(self, queue_id: int) -> QueueItem | None:
        idx = self._index_by_queue_id(queue_id)
        if idx < 0:
            return None
        self._current_index = idx
        item = self.current_item
        self.queue_changed.emit()
        self.current_changed.emit(item)
        return item

    # -------------------------------------------------------------- navigation

    def next_index(self, manual: bool = False) -> int | None:
        if not self._items or self._current_index < 0:
            return None
        if self._repeat == REPEAT_ONE and not manual:
            return self._current_index
        if self._current_index < len(self._items) - 1:
            return self._current_index + 1
        if self._repeat == REPEAT_ALL:
            return 0
        if self._repeat == REPEAT_ONE and manual:
            # Manual next in repeat-one moves to next if possible, else wraps in repeat-all? keep simple: wrap.
            return 0 if len(self._items) > 1 else self._current_index
        return None

    def previous_index(self) -> int | None:
        if not self._items or self._current_index < 0:
            return None
        if self._current_index > 0:
            return self._current_index - 1
        if self._repeat == REPEAT_ALL:
            return len(self._items) - 1
        return 0 if self._current_index == 0 else None

    def advance_next(self, manual: bool = False) -> QueueItem | None:
        idx = self.next_index(manual=manual)
        if idx is None:
            return None
        self._current_index = idx
        item = self.current_item
        self.queue_changed.emit()
        self.current_changed.emit(item)
        return item

    def advance_previous(self) -> QueueItem | None:
        idx = self.previous_index()
        if idx is None:
            return None
        self._current_index = idx
        item = self.current_item
        self.queue_changed.emit()
        self.current_changed.emit(item)
        return item

    # --------------------------------------------------------------- modes

    def set_shuffle(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._shuffle:
            return
        self._shuffle = enabled
        if enabled:
            self._apply_shuffle(keep_current=True)
        else:
            self._restore_original_order(keep_current=True)
        self.shuffle_changed.emit(self._shuffle)
        self.queue_changed.emit()

    def toggle_shuffle(self) -> bool:
        self.set_shuffle(not self._shuffle)
        return self._shuffle

    def set_repeat_mode(self, mode: str) -> None:
        if mode not in REPEAT_MODES:
            return
        if mode == self._repeat:
            return
        self._repeat = mode
        self.repeat_changed.emit(self._repeat)
        self.queue_changed.emit()

    def cycle_repeat_mode(self) -> str:
        idx = REPEAT_MODES.index(self._repeat)
        self.set_repeat_mode(REPEAT_MODES[(idx + 1) % len(REPEAT_MODES)])
        return self._repeat

    # --------------------------------------------------------------- helpers

    def _index_by_queue_id(self, queue_id: int) -> int:
        for i, item in enumerate(self._items):
            if item.queue_id == queue_id:
                return i
        return -1

    def _sync_original_order_to_current(self) -> None:
        # Treat current order as the new base order.
        self._original_order = [i.queue_id for i in self._items]

    def _apply_shuffle(self, keep_current: bool = True) -> None:
        if len(self._items) <= 1:
            return
        current = self.current_item if keep_current else None
        if current is None:
            self._rng.shuffle(self._items)
            self._current_index = 0 if self._items else -1
            return
        before = [i for i in self._items[: self._current_index] if i.queue_id != current.queue_id]
        after = [i for i in self._items[self._current_index + 1 :] if i.queue_id != current.queue_id]
        self._rng.shuffle(after)
        # Keep played-before items in place, shuffle upcoming
        self._items = before + [current] + after
        self._current_index = len(before)

    def _restore_original_order(self, keep_current: bool = True) -> None:
        if not self._original_order:
            self._original_order = [i.queue_id for i in self._items]
        current = self.current_item if keep_current else None
        by_id = {i.queue_id: i for i in self._items}
        ordered = [by_id[qid] for qid in self._original_order if qid in by_id]
        seen = {i.queue_id for i in ordered}
        for i in self._items:
            if i.queue_id not in seen:
                ordered.append(i)
        self._items = ordered
        if current is not None:
            self._current_index = self._index_by_queue_id(current.queue_id)
        elif self._items:
            self._current_index = 0
        else:
            self._current_index = -1

    # ------------------------------------------------------------- aliases
    def get_current_track(self):
        return self.current_item

    def get_upcoming_tracks(self):
        return self.upcoming_items()

    def next_track(self):
        return self.advance_next(manual=True)

    def previous_track(self):
        return self.advance_previous()
