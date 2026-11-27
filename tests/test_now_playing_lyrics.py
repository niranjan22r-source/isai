"""Session 8 tests: Now Playing, Mini Player, Lyrics."""

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
from services.lyrics_service import LyricsService

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


class LyricsServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.svc = LyricsService()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_parse_standard_lrc_and_bom(self) -> None:
        p = self.dir / "song.lrc"
        p.write_bytes(b"\xef\xbb\xbf[ar:Artist]\n[ti:Title]\n[00:01.00]Hello\n[00:02.50][00:03.00]World\n")
        data = self.svc.parse_file(p)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.metadata.get("ar"), "Artist")
        self.assertEqual(len(data.lines), 3)
        self.assertEqual(data.lines[0].time_ms, 1000)
        self.assertEqual(data.lines[1].text, "World")

    def test_invalid_lines_ignored_and_active_index(self) -> None:
        data = self.svc.parse_text("[bad]x\n[00:00.50]A\n[00:01.00]B\n")
        self.assertEqual(len(data.lines), 2)
        self.assertEqual(self.svc.active_line_index(data.lines, 0), -1)
        self.assertEqual(self.svc.active_line_index(data.lines, 500), 0)
        self.assertEqual(self.svc.active_line_index(data.lines, 1500), 1)

    def test_lookup_order(self) -> None:
        audio = self.dir / "track.mp3"
        audio.write_bytes(b"")
        explicit = self.dir / "other.lrc"
        explicit.write_text("[00:00.00]X")
        found = self.svc.find_lyrics(audio, explicit_lrc=explicit)
        self.assertEqual(found, explicit)
        same = self.dir / "track.lrc"
        same.write_text("[00:00.00]Y")
        found2 = self.svc.find_lyrics(audio)
        self.assertEqual(found2, same)


class NowPlayingAndMiniPlayerTests(unittest.TestCase):
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

    def test_now_playing_updates_and_lyrics(self) -> None:
        audio = write_wav(self.dir / "song.wav")
        lrc = self.dir / "song.lrc"
        lrc.write_text("[00:00.00]Line 1\n[00:00.20]Line 2\n")
        tid = self.db.add_track(make_track(audio, title="Song", artist="Art", album="Alb"))
        self.window.refresh_library_views()
        self.window.audio_engine.open_files([str(audio)], autoplay=False)
        self.window.navigate("now_playing")
        page = self.window.pages["now_playing"]
        self.assertEqual(page.title_label.text(), "Song")
        self.assertEqual(page.artist_label.text(), "Art")
        self.assertEqual(page.album_label.text(), "Alb")
        # Lyrics load is deferred off the track-change signal path (singleShot 0).
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        self.assertGreater(page.lyrics_list.count(), 0)

    def test_mini_player_open_restore(self) -> None:
        self.window.show_mini_player()
        QCoreApplication.processEvents()
        self.assertIsNotNone(self.window._mini_player)
        self.assertTrue(self.window._mini_player.isVisible())
        self.assertFalse(self.window.isVisible())
        self.window.restore_from_mini_player()
        QCoreApplication.processEvents()
        self.assertTrue(self.window.isVisible())

    def test_songs_double_click_queues_visible_list(self) -> None:
        p1 = write_wav(self.dir / "a.wav")
        p2 = write_wav(self.dir / "b.wav")
        p3 = write_wav(self.dir / "c.wav")
        for i, p in enumerate([p1, p2, p3], start=1):
            self.db.add_track(make_track(p, title=f"T{i}", track_number=i))
        self.window.refresh_library_views()
        self.window.navigate("songs")
        page = self.window.pages["songs"]
        # Click second row (index 1 in displayed list)
        idx = page.table.model().index(1, 0)
        page._play_from_row(idx)
        QCoreApplication.processEvents()
        tracks = self.window.audio_engine.tracks
        self.assertEqual(len(tracks), 3)
        self.assertIsNotNone(self.window.audio_engine.current_track)


if __name__ == "__main__":
    unittest.main(verbosity=2)
