"""Session 7 tests: queue manager, playback transitions, persistence, UI."""

from __future__ import annotations

import os
import random
import tempfile
import unittest
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

import main
from core.theme_manager import ThemeManager
from services.library_database import LibraryDatabase
from services.queue_manager import QueueManager, REPEAT_ALL, REPEAT_OFF, REPEAT_ONE

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


def write_wav(path: Path, seconds: float = 0.4, rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    nframes = int(seconds * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * nframes)
    return path


def make_track(path: Path, **overrides) -> dict:
    base = {
        "file_path": str(path),
        "title": path.stem,
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Artist",
        "track_number": 1,
        "disc_number": 1,
        "genre": "",
        "year": 2024,
        "duration": 1000,
        "format": "wav",
        "bitrate": 128000,
        "file_size": path.stat().st_size if path.exists() else 100,
        "file_mtime_ns": path.stat().st_mtime_ns if path.exists() else 1,
        "date_added": "2026-01-01T00:00:00+00:00",
        "artwork_path": None,
    }
    base.update(overrides)
    return base


class QueueManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.paths = [write_wav(self.dir / f"t{i}.wav") for i in range(5)]
        self.qm = QueueManager(rng=random.Random(42))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_and_add_many(self) -> None:
        item = self.qm.add_to_queue(self.paths[0])
        self.assertIsNotNone(item)
        self.assertEqual(len(self.qm.items), 1)
        self.qm.add_many_to_queue(self.paths[1:3])
        self.assertEqual(len(self.qm.items), 3)
        self.assertEqual(self.qm.current_index, 0)

    def test_play_next_inserts_after_current(self) -> None:
        self.qm.set_queue(self.paths[:3], start_index=0)
        self.qm.play_next(self.paths[3])
        self.assertEqual(len(self.qm.items), 4)
        self.assertEqual(self.qm.items[1].path, self.paths[3])
        self.assertEqual(self.qm.current_index, 0)

    def test_remove_reorder_clear(self) -> None:
        self.qm.set_queue(self.paths[:4], start_index=1)
        cur_id = self.qm.current_item.queue_id
        # remove non-current
        self.qm.remove_from_queue(self.qm.items[0].queue_id)
        self.assertEqual(len(self.qm.items), 3)
        self.assertEqual(self.qm.current_item.queue_id, cur_id)
        # reorder
        self.assertTrue(self.qm.move_queue_item(0, 2))
        self.assertEqual(self.qm.current_item.queue_id, cur_id)
        self.qm.clear_queue()
        self.assertEqual(len(self.qm.items), 0)
        self.assertIsNone(self.qm.current_item)

    def test_duplicate_tracks_and_stable_ids(self) -> None:
        self.qm.set_queue([self.paths[0], self.paths[0]], start_index=0)
        self.assertEqual(len(self.qm.items), 2)
        self.assertNotEqual(self.qm.items[0].queue_id, self.qm.items[1].queue_id)

    def test_skip_and_empty_invalid(self) -> None:
        self.assertIsNone(self.qm.advance_next())
        self.qm.set_queue(self.paths[:2], start_index=0)
        self.assertIsNone(self.qm.skip_to_queue_item(999999))
        item = self.qm.items[1]
        self.assertIsNotNone(self.qm.skip_to_queue_item(item.queue_id))
        self.assertEqual(self.qm.current_index, 1)

    def test_repeat_modes(self) -> None:
        self.qm.set_queue(self.paths[:2], start_index=1)
        self.qm.set_repeat_mode(REPEAT_OFF)
        self.assertIsNone(self.qm.next_index())
        self.qm.set_repeat_mode(REPEAT_ALL)
        self.assertEqual(self.qm.next_index(), 0)
        self.qm.set_repeat_mode(REPEAT_ONE)
        self.assertEqual(self.qm.next_index(), 1)
        self.assertEqual(self.qm.next_index(manual=True), 0)

    def test_shuffle_keeps_current_and_items(self) -> None:
        self.qm.set_queue(self.paths[:5], start_index=2)
        current_id = self.qm.current_item.queue_id
        before_ids = sorted(i.queue_id for i in self.qm.items)
        self.qm.set_shuffle(True)
        self.assertTrue(self.qm.shuffle)
        self.assertEqual(self.qm.current_item.queue_id, current_id)
        self.assertEqual(sorted(i.queue_id for i in self.qm.items), before_ids)
        self.qm.set_shuffle(False)
        self.assertFalse(self.qm.shuffle)
        self.assertEqual(sorted(i.queue_id for i in self.qm.items), before_ids)

    def test_remove_current_advances_safely(self) -> None:
        self.qm.set_queue(self.paths[:3], start_index=1)
        cur = self.qm.current_item
        next_item = self.qm.items[2]
        self.qm.remove_from_queue(cur.queue_id)
        self.assertEqual(self.qm.current_item.queue_id, next_item.queue_id)


class QueuePersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.p1 = write_wav(self.dir / "a.wav")
        self.p2 = write_wav(self.dir / "b.wav")
        self.id1 = self.db.add_track(make_track(self.p1, title="A"))
        self.id2 = self.db.add_track(make_track(self.p2, title="B"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_save_and_restore_queue(self) -> None:
        items = [
            {"queue_order": 0, "track_id": self.id1, "file_path": str(self.p1), "title": "A", "artist": "Artist", "album": "Album", "duration": 1000, "artwork_path": None},
            {"queue_order": 1, "track_id": self.id2, "file_path": str(self.p2), "title": "B", "artist": "Artist", "album": "Album", "duration": 1000, "artwork_path": None},
        ]
        self.db.save_queue_state(items, 1, 1234, True, "all", str(self.p2))
        state = self.db.load_queue_state()
        self.assertIsNotNone(state)
        self.assertEqual(len(state["items"]), 2)
        self.assertEqual(state["current_queue_index"], 1)
        self.assertEqual(state["current_position_ms"], 1234)
        self.assertTrue(state["shuffle_enabled"])
        self.assertEqual(state["repeat_mode"], "all")

    def test_restore_skips_missing_files(self) -> None:
        missing = str(self.dir / "missing.wav")
        items = [
            {"queue_order": 0, "track_id": self.id1, "file_path": str(self.p1), "title": "A", "artist": "", "album": "", "duration": 0, "artwork_path": None},
            {"queue_order": 1, "track_id": 9999, "file_path": missing, "title": "M", "artist": "", "album": "", "duration": 0, "artwork_path": None},
        ]
        self.db.save_queue_state(items, 1, 0, False, "off", missing)
        state = self.db.load_queue_state()
        self.assertEqual(len(state["items"]), 1)
        self.assertEqual(state["current_queue_index"], 0)


class QueueUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.settings = QSettings(str(self.dir / "settings.ini"), QSettings.Format.IniFormat)
        self.theme = ThemeManager(self.settings)
        self.window = main.MainWindow(self.theme, library_db=self.db)
        self.window.show()

    def tearDown(self) -> None:
        try:
            self.window.audio_engine.stop()
        except Exception:
            pass
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def test_queue_panel_toggle_and_updates(self) -> None:
        self.assertFalse(self.window.queue_panel.isVisible())
        self.window._toggle_queue_panel(True)
        self.assertTrue(self.window.queue_panel.isVisible())
        p = write_wav(self.dir / "q.wav")
        self.window.audio_engine.open_files([str(p)], autoplay=False)
        QCoreApplication.processEvents()
        self.window.queue_panel.refresh_queue()
        self.assertGreater(self.window.queue_panel.list.count(), 0)

    def test_shuffle_repeat_shortcuts_state(self) -> None:
        qm = self.window.audio_engine.queue_manager
        self.assertFalse(qm.shuffle)
        qm.toggle_shuffle()
        self.assertTrue(qm.shuffle)
        qm.cycle_repeat_mode()
        self.assertEqual(qm.repeat_mode, REPEAT_ALL)
        qm.cycle_repeat_mode()
        self.assertEqual(qm.repeat_mode, REPEAT_ONE)
        qm.cycle_repeat_mode()
        self.assertEqual(qm.repeat_mode, REPEAT_OFF)

    def test_restore_queue_paused(self) -> None:
        p = write_wav(self.dir / "r.wav")
        tid = self.db.add_track(make_track(p, title="R"))
        items = [{"queue_order": 0, "track_id": tid, "file_path": str(p), "title": "R", "artist": "A", "album": "Al", "duration": 400, "artwork_path": None}]
        self.db.save_queue_state(items, 0, 0, False, "off", str(p))
        # create new window to restore
        w2 = main.MainWindow(self.theme, library_db=self.db)
        w2.show()
        QCoreApplication.processEvents()
        self.assertIsNotNone(w2.audio_engine.current_track)
        self.assertEqual(w2.audio_engine.playback_state, "stopped")
        w2.audio_engine.stop()
        w2.close()
        w2.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main(verbosity=2)
