"""Session 6 tests: playlists and favorites."""

from __future__ import annotations

import os
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


class PlaylistDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.p1 = write_wav(self.dir / "a.wav")
        self.p2 = write_wav(self.dir / "b.wav")
        self.p3 = write_wav(self.dir / "c.wav")
        self.id1 = self.db.add_track(make_track(self.p1, title="A"))
        self.id2 = self.db.add_track(make_track(self.p2, title="B"))
        self.id3 = self.db.add_track(make_track(self.p3, title="C"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_empty_duplicate_rename_delete(self) -> None:
        pid = self.db.create_playlist("Road Trip", "desc")
        self.assertGreater(pid, 0)
        with self.assertRaises(ValueError):
            self.db.create_playlist("  ")
        with self.assertRaises(ValueError):
            self.db.create_playlist("road trip")
        self.assertTrue(self.db.rename_playlist(pid, "Road Trip 2"))
        pls = self.db.get_playlists()
        self.assertEqual(pls[0].name, "Road Trip 2")
        self.assertTrue(self.db.delete_playlist(pid))
        self.assertEqual(self.db.get_playlists(), [])

    def test_add_remove_reorder_tracks(self) -> None:
        pid = self.db.create_playlist("P1")
        self.assertTrue(self.db.add_track_to_playlist(pid, self.id1))
        self.assertTrue(self.db.add_track_to_playlist(pid, self.id2))
        self.assertFalse(self.db.add_track_to_playlist(pid, self.id1))  # duplicate
        tracks = self.db.get_playlist_tracks(pid)
        self.assertEqual([t.id for t in tracks], [self.id1, self.id2])
        self.assertTrue(self.db.reorder_playlist_tracks(pid, [self.id2, self.id1]))
        tracks = self.db.get_playlist_tracks(pid)
        self.assertEqual([t.id for t in tracks], [self.id2, self.id1])
        self.assertTrue(self.db.remove_track_from_playlist(pid, self.id2))
        tracks = self.db.get_playlist_tracks(pid)
        self.assertEqual([t.id for t in tracks], [self.id1])

    def test_persistence_and_invalid_ids(self) -> None:
        pid = self.db.create_playlist("Persist")
        self.db.add_track_to_playlist(pid, self.id1)
        db2 = LibraryDatabase(self.dir / "lib.db")
        pls = db2.get_playlists()
        self.assertEqual(len(pls), 1)
        self.assertEqual(pls[0].track_count, 1)
        self.assertEqual([t.id for t in db2.get_playlist_tracks(pid)], [self.id1])
        self.assertFalse(db2.add_track_to_playlist(9999, self.id1))
        self.assertFalse(db2.add_track_to_playlist(pid, 9999))
        self.assertFalse(db2.remove_track_from_playlist(pid, 9999))
        self.assertFalse(db2.rename_playlist(9999, "X"))


class FavoritesDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.p1 = write_wav(self.dir / "a.wav")
        self.id1 = self.db.add_track(make_track(self.p1, title="A"))
        self.id2 = self.db.add_track(make_track(write_wav(self.dir / "b.wav"), title="B"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_remove_check_duplicates_count(self) -> None:
        self.assertTrue(self.db.add_favorite(self.id1))
        self.assertFalse(self.db.add_favorite(self.id1))
        self.assertTrue(self.db.is_favorite(self.id1))
        self.assertEqual(self.db.get_favorite_count(), 1)
        favs = self.db.get_favorites()
        self.assertEqual([t.id for t in favs], [self.id1])
        self.assertTrue(self.db.remove_favorite(self.id1))
        self.assertFalse(self.db.is_favorite(self.id1))
        self.assertEqual(self.db.get_favorite_count(), 0)

    def test_persistence_after_restart(self) -> None:
        self.db.add_favorite(self.id2)
        db2 = LibraryDatabase(self.dir / "lib.db")
        self.assertTrue(db2.is_favorite(self.id2))
        self.assertEqual(db2.get_favorite_count(), 1)


class PlaylistFavoritesUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.settings = QSettings(str(self.dir / "settings.ini"), QSettings.Format.IniFormat)
        self.theme = ThemeManager(self.settings)
        self.window = main.MainWindow(self.theme, library_db=self.db)
        self.window.show()

    def tearDown(self) -> None:
        self.window.audio_engine.stop()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def _add_track(self, name="t.wav", title="T", artist="A"):
        p = write_wav(self.dir / name)
        tid = self.db.add_track(make_track(p, title=title, artist=artist))
        self.window.refresh_library_views()
        return tid, p

    def test_create_playlist_and_show_in_page(self) -> None:
        pid = self.db.create_playlist("My Playlist")
        self.window.refresh_library_views()
        page = self.window.pages["playlists"]
        self.assertGreater(page.playlist_table.rowCount(), 0)
        self.assertEqual(page.playlist_table.item(0, 0).text(), "My Playlist")

    def test_favorite_button_and_page_update(self) -> None:
        tid, path = self._add_track("fav.wav", "Fav Song")
        self.window.audio_engine.open_files([str(path)], autoplay=False)
        self.window.player_bar.refresh_favorite_state()
        self.assertTrue(self.window.player_bar.favorite_button.isEnabled())
        self.window.player_bar._toggle_favorite()
        self.assertTrue(self.db.is_favorite(tid))
        self.window.refresh_library_views()
        fav_page = self.window.pages["favorites"]
        self.assertEqual(fav_page.table.rowCount(), 1)

    def test_play_playlist(self) -> None:
        tid1, p1 = self._add_track("p1.wav", "P1")
        tid2, p2 = self._add_track("p2.wav", "P2")
        pid = self.db.create_playlist("PlayMe")
        self.db.add_track_to_playlist(pid, tid1)
        self.db.add_track_to_playlist(pid, tid2)
        self.window.refresh_library_views()
        page = self.window.pages["playlists"]
        page._open_playlist(pid)
        page._play_all()
        self.assertIsNotNone(self.window.audio_engine.current_track)


if __name__ == "__main__":
    unittest.main(verbosity=2)
