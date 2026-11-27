"""Session 11 tests: settings, library folders, cache safety, DB stats."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

import main
from core.app_settings import (
    DEFAULT_SHUFFLE_KEY,
    DEFAULT_REPEAT_KEY,
    PLAYBACK_NOTIFICATIONS_KEY,
    REMEMBER_STATE_KEY,
    RESUME_POSITION_KEY,
    SCAN_ON_STARTUP_KEY,
    VOLUME_KEY,
    get_setting,
    set_setting,
)
from core.theme_manager import ThemeManager
from services.artwork_cache import ArtworkCache
from services.library_database import LibraryDatabase

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


class AppSettingsTests(unittest.TestCase):
    def test_defaults_and_invalid_recovery(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        s = QSettings(str(Path(tmp.name) / "s.ini"), QSettings.Format.IniFormat)
        self.assertEqual(get_setting(s, VOLUME_KEY, 70), 70)
        self.assertEqual(get_setting(s, DEFAULT_REPEAT_KEY, "off"), "off")
        s.setValue(VOLUME_KEY, "999")
        self.assertEqual(get_setting(s, VOLUME_KEY, 70), 100)
        s.setValue(VOLUME_KEY, "garbage")
        self.assertEqual(get_setting(s, VOLUME_KEY, 70), 70)
        s.setValue(DEFAULT_REPEAT_KEY, "bogus")
        self.assertEqual(get_setting(s, DEFAULT_REPEAT_KEY, "off"), "off")
        set_setting(s, DEFAULT_SHUFFLE_KEY, True)
        self.assertTrue(get_setting(s, DEFAULT_SHUFFLE_KEY, False))

    def test_settings_persist_across_instances(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = str(Path(tmp.name) / "s.ini")
        s1 = QSettings(path, QSettings.Format.IniFormat)
        set_setting(s1, VOLUME_KEY, 42)
        set_setting(s1, REMEMBER_STATE_KEY, False)
        set_setting(s1, RESUME_POSITION_KEY, False)
        set_setting(s1, SCAN_ON_STARTUP_KEY, True)
        set_setting(s1, PLAYBACK_NOTIFICATIONS_KEY, False)
        s1.sync()
        s2 = QSettings(path, QSettings.Format.IniFormat)
        self.assertEqual(get_setting(s2, VOLUME_KEY, 70), 42)
        self.assertFalse(get_setting(s2, REMEMBER_STATE_KEY, True))
        self.assertFalse(get_setting(s2, RESUME_POSITION_KEY, True))
        self.assertTrue(get_setting(s2, SCAN_ON_STARTUP_KEY, False))
        self.assertFalse(get_setting(s2, PLAYBACK_NOTIFICATIONS_KEY, True))


class LibraryFoldersAndStatsTests(unittest.TestCase):
    def test_library_folders_register_remove(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = LibraryDatabase(Path(tmp.name) / "lib.db")
        folder = Path(tmp.name) / "Music"
        folder.mkdir()
        self.assertTrue(db.add_library_folder(folder))
        self.assertFalse(db.add_library_folder(folder))
        self.assertEqual(db.get_library_folders(), [str(folder)])
        self.assertTrue(db.remove_library_folder(folder))
        self.assertEqual(db.get_library_folders(), [])

    def test_library_stats(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = LibraryDatabase(Path(tmp.name) / "lib.db")
        p = Path(tmp.name) / "a.wav"
        p.write_bytes(b"RIFF")
        db.add_track({
            "file_path": str(p), "title": "T", "artist": "A", "album": "Al", "album_artist": "A",
            "track_number": 1, "disc_number": 1, "genre": "", "year": 2026, "duration": 1000,
            "format": "wav", "bitrate": 320, "file_size": 4, "file_mtime_ns": 1,
            "date_added": "2026-01-01T00:00:00+00:00", "artwork_path": None,
        })
        stats = db.get_library_stats()
        self.assertEqual(stats["tracks"], 1)
        self.assertEqual(stats["albums"], 1)
        self.assertEqual(stats["artists"], 1)


class ArtworkCacheSafetyTests(unittest.TestCase):
    def test_clear_cache_does_not_delete_db_or_music(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        db = LibraryDatabase(root / "lib.db")
        music = root / "song.wav"
        music.write_bytes(b"RIFFfake")
        art_dir = root / "artwork"
        cache = ArtworkCache(art_dir)
        art_path = cache.store(b"\x89PNG\r\n\x1a\nfake", "image/png")
        self.assertIsNotNone(art_path)
        db.add_track({
            "file_path": str(music), "title": "T", "artist": "A", "album": "Al", "album_artist": "A",
            "track_number": 1, "disc_number": 1, "genre": "", "year": 2026, "duration": 1000,
            "format": "wav", "bitrate": 320, "file_size": music.stat().st_size, "file_mtime_ns": 1,
            "date_added": "2026-01-01T00:00:00+00:00", "artwork_path": art_path,
        })
        files, freed = cache.clear()
        self.assertGreaterEqual(files, 1)
        self.assertGreaterEqual(freed, 1)
        self.assertTrue(music.exists())
        self.assertTrue(db.db_path.exists())
        self.assertEqual(db.track_count(), 1)
        # stale path should be resolvable as missing
        self.assertIsNone(cache.resolve(art_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
