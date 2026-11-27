"""Tests for embedded audio lyrics extraction and Now Playing integration."""

from __future__ import annotations

import os
import tempfile
import unittest
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mutagen.id3 import ID3, SYLT, USLT, TXXX, Encoding
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

import main
from core.theme_manager import ThemeManager
from services.library_database import LibraryDatabase
from services.lyrics_service import LyricsService
from services.metadata_reader import extract_embedded_lyrics

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


def write_wav(path: Path, seconds: float = 0.2, rate: int = 22050) -> Path:
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
        "format": path.suffix.lstrip(".").lower() or "wav",
        "bitrate": 128000,
        "file_size": path.stat().st_size if path.exists() else 100,
        "file_mtime_ns": path.stat().st_mtime_ns if path.exists() else 1,
        "date_added": "2026-01-01T00:00:00+00:00",
        "artwork_path": None,
    }
    base.update(overrides)
    return base


class EmbeddedLyricsExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _mp3(self, name: str = "song.mp3") -> Path:
        p = self.dir / name
        p.write_bytes(b"")
        return p

    def test_mp3_lyrics_tam_txxx(self) -> None:
        p = self._mp3("tamil.mp3")
        tags = ID3()
        tamil = "வணக்கம்\nஇது வரி இரண்டு\n\nஇது மூன்றாம் வரி"
        tags.add(TXXX(encoding=Encoding.UTF8, desc="lyrics-tam", text=[tamil]))
        tags.save(str(p))
        cands = extract_embedded_lyrics(p)
        self.assertTrue(cands)
        self.assertEqual(cands[0]["text"], tamil)
        svc = LyricsService()
        data = svc.load_for_track(p)
        self.assertIsNotNone(data)
        assert data is not None
        texts = [l.text for l in data.lines]
        self.assertEqual(texts[0], "வணக்கம்")
        self.assertEqual(texts[1], "இது வரி இரண்டு")
        self.assertEqual(texts[2], "")  # blank line preserved
        self.assertEqual(texts[3], "இது மூன்றாம் வரி")
        self.assertFalse(data.is_synced)

    def test_mp3_standard_uslt(self) -> None:
        p = self._mp3("uslt.mp3")
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="Hello\nWorld"))
        tags.save(str(p))
        cands = extract_embedded_lyrics(p)
        self.assertTrue(any(c.get("text") == "Hello\nWorld" for c in cands))
        data = LyricsService().load_for_track(p)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual([l.text for l in data.lines], ["Hello", "World"])

    def test_audio_without_lyrics(self) -> None:
        p = self._mp3("nolyrics.mp3")
        ID3().save(str(p))
        self.assertEqual(extract_embedded_lyrics(p), [])
        self.assertIsNone(LyricsService().load_for_track(p))

    def test_empty_lyrics_metadata(self) -> None:
        p = self._mp3("empty.mp3")
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="   \n  "))
        tags.save(str(p))
        self.assertEqual(extract_embedded_lyrics(p), [])
        self.assertIsNone(LyricsService().load_for_track(p))

    def test_tamil_unicode_preserved(self) -> None:
        p = self._mp3("unicode.mp3")
        tamil = "தமிழ் பாடல் வரிகள்\nஇரண்டாம் வரி"
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="tam", desc="", text=tamil))
        tags.save(str(p))
        data = LyricsService().load_for_track(p)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertIn("தமிழ் பாடல் வரிகள்", data.lines[0].text)
        self.assertEqual(data.lines[1].text, "இரண்டாம் வரி")

    def test_multiple_embedded_lyrics_fields_no_duplicate(self) -> None:
        p = self._mp3("multi.mp3")
        text = "Same lyrics"
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text=text))
        tags.add(TXXX(encoding=Encoding.UTF8, desc="LYRICS", text=[text]))
        tags.save(str(p))
        cands = extract_embedded_lyrics(p)
        # dedup should prevent exact duplicates
        texts = [c.get("text") for c in cands if c.get("text")]
        self.assertEqual(texts.count("Same lyrics"), 1)

    def test_multiline_and_blank_lines_preserved(self) -> None:
        p = self._mp3("blank.mp3")
        text = "Line 1\n\nLine 3\n  \nLine 5"
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text=text))
        tags.save(str(p))
        data = LyricsService().load_for_track(p)
        self.assertIsNotNone(data)
        assert data is not None
        texts = [l.text for l in data.lines]
        self.assertEqual(texts[0], "Line 1")
        self.assertEqual(texts[1], "")
        self.assertEqual(texts[2], "Line 3")

    def test_malformed_metadata_safe(self) -> None:
        p = self.dir / "bad.mp3"
        p.write_bytes(b"\xff\xfb\x00\x00garbage-not-id3")
        # should not raise
        cands = extract_embedded_lyrics(p)
        self.assertIsInstance(cands, list)
        data = LyricsService().load_for_track(p)
        # no crash; may be None
        self.assertTrue(data is None or hasattr(data, "lines"))


class LyricsPriorityAndLrcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.svc = LyricsService()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_existing_lrc_functionality(self) -> None:
        audio = self.dir / "song.wav"
        audio.write_bytes(b"")
        lrc = self.dir / "song.lrc"
        lrc.write_text("[00:01.00]Hello\n[00:02.00]World\n", encoding="utf-8")
        data = self.svc.load_for_track(audio)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertTrue(data.is_synced)
        self.assertEqual(data.lines[0].text, "Hello")

    def test_embedded_takes_precedence_when_no_lrc(self) -> None:
        p = self.dir / "song.mp3"
        p.write_bytes(b"")
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="Embedded line"))
        tags.save(str(p))
        data = self.svc.load_for_track(p)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.lines[0].text, "Embedded line")
        self.assertEqual(data.source_type, "embedded-text")

    def test_explicit_lrc_overrides_embedded(self) -> None:
        p = self.dir / "song.mp3"
        p.write_bytes(b"")
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="Embedded"))
        tags.save(str(p))
        lrc = self.dir / "other.lrc"
        lrc.write_text("[00:00.00]Explicit\n", encoding="utf-8")
        data = self.svc.load_for_track(p, explicit_lrc=lrc)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.lines[0].text, "Explicit")
        self.assertEqual(data.source_type, "lrc")


class NowPlayingEmbeddedLyricsIntegrationTests(unittest.TestCase):
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
        QCoreApplication.processEvents()
        self.tmp.cleanup()

    def test_embedded_tamil_lyrics_displayed(self) -> None:
        audio = self.dir / "tamil.mp3"
        audio.write_bytes(b"")
        tags = ID3()
        tags.add(TXXX(encoding=Encoding.UTF8, desc="lyrics-tam", text=["வணக்கம்\nவரி இரண்டு"]))
        tags.save(str(audio))
        self.db.add_track(make_track(audio, title="Tamil Song", artist="Art", album="Alb", format="mp3"))
        self.window.refresh_library_views()
        self.window.audio_engine.open_files([str(audio)], autoplay=False)
        self.window.navigate("now_playing")
        page = self.window.pages["now_playing"]
        # Lyrics load is deferred off the track-change signal path (singleShot 0).
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        self.assertGreater(page.lyrics_list.count(), 0)
        self.assertEqual(page.lyrics_list.item(0).text(), "வணக்கம்")
        self.assertFalse(page.lyrics_status.isVisible())

    def test_track_switch_updates_lyrics_and_empty_state(self) -> None:
        a1 = self.dir / "with.mp3"
        a1.write_bytes(b"")
        tags = ID3()
        tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="First song lyrics"))
        tags.save(str(a1))
        a2 = self.dir / "without.mp3"
        a2.write_bytes(b"")
        ID3().save(str(a2))
        self.db.add_track(make_track(a1, title="With", file_mtime_ns=1))
        self.db.add_track(make_track(a2, title="Without", file_mtime_ns=2))
        self.window.refresh_library_views()
        self.window.audio_engine.open_files([str(a1), str(a2)], autoplay=False)
        self.window.navigate("now_playing")
        page = self.window.pages["now_playing"]
        # Lyrics load is deferred off the track-change signal path (singleShot 0).
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        self.assertEqual(page.lyrics_list.item(0).text(), "First song lyrics")
        # Switch to track without lyrics
        items = self.window.audio_engine.queue_manager.items
        self.assertGreaterEqual(len(items), 2)
        self.window.audio_engine.skip_to_queue_id(items[1].queue_id, autoplay=False)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()
        self.assertTrue(page.lyrics_status.isVisible())
        self.assertEqual(page.lyrics_status.text(), "Lyrics aren't available for this track.")
        self.assertFalse(page.lyrics_list.isVisible())


if __name__ == "__main__":
    unittest.main(verbosity=2)
