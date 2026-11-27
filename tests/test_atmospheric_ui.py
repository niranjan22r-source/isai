"""Atmospheric redesign regression tests: seek ownership, queue order, lists."""

from __future__ import annotations

import os
import tempfile
import unittest
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings, Qt
from PySide6.QtWidgets import QApplication

import main
from core.theme_manager import DARK, LIGHT, ThemeManager
from services.library_database import LibraryDatabase

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


def pump() -> None:
    assert _app is not None
    _app.processEvents()


def write_wav(path: Path, seconds: float = 0.2, rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


class AtmosphericUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.settings = QSettings(
            str(self.dir / "settings.ini"), QSettings.Format.IniFormat
        )
        self.theme = ThemeManager(self.settings)
        self.window = main.MainWindow(self.theme, library_db=self.db)
        self.window.show()
        pump()

    def tearDown(self) -> None:
        try:
            if self.window._mini_player is not None:
                self.window._mini_player._on_restore = None
                self.window._mini_player.close()
        except Exception:
            pass
        try:
            self.window.audio_engine.stop()
        except Exception:
            pass
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    # ----------------------------------------------------------- seek ownership

    def test_bottom_seek_row_yields_to_now_playing(self) -> None:
        self.window.navigate("home")
        pump()
        self.assertFalse(self.window.player_bar.progress_row.isHidden())
        self.window.navigate("now_playing")
        pump()
        self.assertTrue(self.window.player_bar.progress_row.isHidden())
        # The Now Playing page owns a live seek slider in its place.
        page = self.window.pages["now_playing"]
        self.assertFalse(page.progress.isHidden())
        self.window.navigate("songs")
        pump()
        self.assertFalse(self.window.player_bar.progress_row.isHidden())

    # ------------------------------------------------------------- queue order

    def _queue_paths(self, count: int = 5) -> list[Path]:
        return [write_wav(self.dir / f"track{i}.wav") for i in range(count)]

    def test_shuffle_upcoming_and_restore_intended_order(self) -> None:
        paths = self._queue_paths()
        engine = self.window.audio_engine
        engine.open_files([str(p) for p in paths], autoplay=False, start_index=2)
        qm = engine.queue_manager
        pump()
        original_ids = [item.queue_id for item in qm.items]
        current_id = qm.current_item.queue_id

        self.window.navigate("songs")
        pump()
        qm.set_shuffle(True)
        pump()
        self.assertTrue(qm.shuffle)
        self.assertEqual(qm.current_item.queue_id, current_id)
        self.assertEqual(
            [item.queue_id for item in qm.items[: qm.current_index + 1]],
            original_ids[:3],
            "shuffle must leave the current item and history untouched",
        )
        first_upcoming = qm.items[qm.current_index + 1].queue_id
        self.assertEqual(qm.next_index(manual=True), qm.current_index + 1)

        # The visible queue follows the manager, and Next plays the first
        # visible upcoming row.
        self.window.queue_panel.refresh_queue()
        visible_ids = [
            self.window.queue_panel.list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.window.queue_panel.list.count())
        ]
        self.assertEqual(visible_ids, [item.queue_id for item in qm.items])
        engine.next_track()
        pump()
        self.assertEqual(qm.current_item.queue_id, first_upcoming)

        qm.set_shuffle(False)
        pump()
        self.assertEqual([item.queue_id for item in qm.items], original_ids)

    def test_reorder_while_shuffled_keeps_intended_base_order(self) -> None:
        paths = self._queue_paths(6)
        engine = self.window.audio_engine
        engine.open_files([str(p) for p in paths], autoplay=False, start_index=1)
        qm = engine.queue_manager
        pump()
        base_ids = [item.queue_id for item in qm.items]
        qm.set_shuffle(True)
        pump()
        self.assertTrue(qm.move_queue_item(0, len(qm.items) - 1))
        qm.set_shuffle(False)
        pump()
        self.assertEqual([item.queue_id for item in qm.items], base_ids)

    def test_queue_panel_reorder_uses_authoritative_model(self) -> None:
        paths = self._queue_paths(4)
        engine = self.window.audio_engine
        engine.open_files([str(p) for p in paths], autoplay=False, start_index=0)
        qm = engine.queue_manager
        self.window._toggle_queue_panel(True)
        self.window.queue_panel.refresh_queue()
        panel = self.window.queue_panel
        first = qm.items[0].queue_id
        second = qm.items[1].queue_id
        panel.list.setCurrentRow(0)
        panel._move_selected(1)
        pump()
        self.assertEqual(
            [item.queue_id for item in qm.items][:2], [second, first]
        )
        self.assertEqual(panel.list.count(), 4)
        self.assertEqual(
            panel.list.item(0).data(Qt.ItemDataRole.UserRole), second
        )

    # ------------------------------------------------------------------ lists

    def test_song_rows_are_readable(self) -> None:
        p = write_wav(self.dir / "song.wav")
        self.db.add_track(
            {
                "file_path": str(p),
                "title": "Readable",
                "artist": "Artist",
                "album": "Album",
                "album_artist": "Artist",
                "track_number": 1,
                "disc_number": 1,
                "genre": "",
                "year": 2026,
                "duration": 200,
                "format": "wav",
                "bitrate": 320,
                "file_size": p.stat().st_size,
                "file_mtime_ns": p.stat().st_mtime_ns,
                "date_added": "2026-01-01T00:00:00+00:00",
                "artwork_path": None,
            }
        )
        self.window.refresh_library_views()
        page = self.window.pages["songs"]
        self.assertGreaterEqual(page.table.verticalHeader().defaultSectionSize(), 48)
        self.assertGreaterEqual(page.table.iconSize().height(), 36)

    def test_home_and_now_playing_are_designed_surfaces(self) -> None:
        home = self.window.pages["home"]
        self.assertTrue(hasattr(home, "hero"))
        self.assertEqual(home.hero.objectName(), "heroPanel")
        now = self.window.pages["now_playing"]
        self.assertTrue(hasattr(now, "canvas"))
        self.assertEqual(now.canvas.objectName(), "nowPlayingCanvas")

    def test_light_theme_is_intentionally_designed(self) -> None:
        self.theme.set_theme(DARK)
        dark = self.theme.colors
        self.theme.set_theme(LIGHT)
        light = self.theme.colors
        self.assertNotEqual(dark.bg, light.bg)
        self.assertNotEqual(dark.accent, light.accent)
        # Clean light theme: bright background; dark theme: deep background.
        self.assertGreater(int(light.bg[1:3], 16), 200)
        self.assertLess(int(dark.bg[1:3], 16), 40)

    def test_recent_page_table_expands_vertically(self) -> None:
        for i in range(15):
            p = write_wav(self.dir / f"r{i}.wav")
            self.db.add_track(
                {
                    "file_path": str(p),
                    "title": f"Track {i}",
                    "artist": "Artist",
                    "album": "Album",
                    "album_artist": "Artist",
                    "track_number": i + 1,
                    "disc_number": 1,
                    "genre": "",
                    "year": 2026,
                    "duration": 200,
                    "format": "wav",
                    "bitrate": 320,
                    "file_size": p.stat().st_size,
                    "file_mtime_ns": p.stat().st_mtime_ns,
                    "date_added": "2026-01-01T00:00:00+00:00",
                    "artwork_path": None,
                }
            )
            self.db.mark_played(str(p), f"2026-11-27T00:00:{i:02d}+00:00")
        self.window.refresh_library_views()
        self.window.navigate("recent")
        page = self.window.pages["recent"]
        self.window.resize(1200, 760)
        pump(); pump()
        h760 = page.table.height()
        self.window.resize(1200, 900)
        pump(); pump()
        h900 = page.table.height()
        self.window.resize(1000, 650)
        pump(); pump()
        h650 = page.table.height()
        self.assertGreater(h900, h760)
        self.assertLess(h650, h760)
        self.assertGreater(h760, 350)


if __name__ == "__main__":
    unittest.main(verbosity=2)
