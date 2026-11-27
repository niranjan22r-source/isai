"""Session 4 tests: library database, metadata, artwork, scanning, and UI integration."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication

import main
from services.artwork_cache import ArtworkCache
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase, SUPPORTED_EXTENSIONS
from services.metadata_reader import UNKNOWN_ALBUM, UNKNOWN_ARTIST, extract_metadata, is_supported_audio_file
from services.music_scanner import MusicScannerWorker

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


def pump(delay: float = 0.01) -> None:
    assert _app is not None
    _app.processEvents()
    time.sleep(delay)


def wait_until(predicate, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        pump()
    return bool(predicate())


def write_wav(path: Path, seconds: float = 0.5, rate: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    nframes = int(seconds * rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        # silence is fine; metadata/duration is what we need
        wf.writeframes(b"\x00\x00" * nframes)
    return path


def make_track(path: str, **overrides) -> dict:
    base = {
        "file_path": path,
        "title": Path(path).stem,
        "artist": UNKNOWN_ARTIST,
        "album": UNKNOWN_ALBUM,
        "album_artist": UNKNOWN_ARTIST,
        "track_number": None,
        "disc_number": None,
        "genre": "",
        "year": None,
        "duration": 1000,
        "format": Path(path).suffix.lower().lstrip("."),
        "bitrate": None,
        "file_size": 123,
        "file_mtime_ns": 1,
        "date_added": "2026-01-01T00:00:00+00:00",
        "artwork_path": None,
    }
    base.update(overrides)
    return base


class LibraryDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "library.db"
        self.db = LibraryDatabase(self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_initialization_creates_database(self) -> None:
        self.assertTrue(self.db_path.exists())
        self.assertEqual(self.db.track_count(), 0)

    def test_insert_and_retrieve_track(self) -> None:
        track = make_track(str(Path(self.tmp.name) / "song.mp3"), title="Song", artist="Artist", album="Album")
        track_id = self.db.add_track(track)
        self.assertGreater(track_id, 0)
        got = self.db.get_track(track_id)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.title, "Song")
        self.assertEqual(got.artist, "Artist")
        self.assertEqual(got.album, "Album")
        by_path = self.db.get_track_by_path(track["file_path"])
        self.assertIsNotNone(by_path)
        assert by_path is not None
        self.assertEqual(by_path.id, track_id)

    def test_duplicate_file_path_protection(self) -> None:
        path = str(Path(self.tmp.name) / "dup.mp3")
        self.db.add_track(make_track(path, title="First"))
        with self.assertRaises(Exception):
            self.db.add_track(make_track(path, title="Second"))
        self.assertEqual(self.db.track_count(), 1)
        self.db.upsert_track(make_track(path, title="Second"))
        self.assertEqual(self.db.track_count(), 1)
        got = self.db.get_track_by_path(path)
        assert got is not None
        self.assertEqual(got.title, "Second")

    def test_update_and_delete_track(self) -> None:
        path = str(Path(self.tmp.name) / "up.mp3")
        track_id = self.db.add_track(make_track(path, title="Old"))
        self.assertTrue(self.db.update_track(track_id, title="New", artist="A"))
        got = self.db.get_track(track_id)
        assert got is not None
        self.assertEqual(got.title, "New")
        self.assertEqual(got.artist, "A")
        self.assertTrue(self.db.remove_track(track_id))
        self.assertIsNone(self.db.get_track(track_id))
        self.assertEqual(self.db.track_count(), 0)

    def test_persistence_across_connections(self) -> None:
        path = str(Path(self.tmp.name) / "persist.mp3")
        self.db.add_track(make_track(path, title="Persisted"))
        db2 = LibraryDatabase(self.db_path)
        got = db2.get_track_by_path(path)
        self.assertIsNotNone(got)
        assert got is not None
        self.assertEqual(got.title, "Persisted")

    def test_search_and_summaries(self) -> None:
        base = Path(self.tmp.name)
        self.db.add_track(make_track(str(base / "a.mp3"), title="Alpha", artist="Artist1", album="Album1", genre="Rock", date_added="2026-01-01T00:00:00+00:00"))
        self.db.add_track(make_track(str(base / "b.mp3"), title="Beta", artist="Artist2", album="Album2", genre="Jazz", date_added="2026-01-02T00:00:00+00:00"))
        self.db.mark_played(str(base / "b.mp3"), "2026-01-03T00:00:00+00:00")
        results = self.db.search_tracks("alp")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Alpha")
        recent = self.db.get_recently_added(limit=1)
        self.assertEqual(recent[0].title, "Beta")
        played = self.db.get_recently_played(limit=10)
        self.assertEqual(len(played), 1)
        self.assertEqual(played[0].title, "Beta")
        albums = self.db.get_albums()
        artists = self.db.get_artists()
        self.assertEqual(len(albums), 2)
        self.assertEqual(len(artists), 2)


class MetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_supported_extension_detection(self) -> None:
        for ext in [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"]:
            self.assertTrue(is_supported_audio_file(f"track{ext}"))
        for ext in [".txt", ".jpg", ".py", ".mp4"]:
            self.assertFalse(is_supported_audio_file(f"track{ext}"))
        self.assertEqual(SUPPORTED_EXTENSIONS, {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"})

    def test_missing_metadata_fallback(self) -> None:
        wav = write_wav(self.dir / "My Song.wav")
        meta = extract_metadata(wav)
        self.assertEqual(meta["title"], "My Song")
        self.assertEqual(meta["artist"], UNKNOWN_ARTIST)
        self.assertEqual(meta["album"], UNKNOWN_ALBUM)
        self.assertEqual(meta["format"], "wav")
        self.assertGreater(meta["duration"], 0)
        self.assertGreater(meta["file_size"], 0)

    def test_malformed_file_does_not_raise(self) -> None:
        bad = self.dir / "broken.mp3"
        bad.write_bytes(b"not an audio file")
        meta = extract_metadata(bad)
        self.assertEqual(meta["title"], "broken")
        self.assertEqual(meta["artist"], UNKNOWN_ARTIST)
        self.assertEqual(meta["album"], UNKNOWN_ALBUM)

    def test_missing_file_returns_fallback(self) -> None:
        missing = self.dir / "missing.flac"
        meta = extract_metadata(missing)
        self.assertEqual(meta["title"], "missing")
        self.assertEqual(meta["artist"], UNKNOWN_ARTIST)


class ArtworkCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = ArtworkCache(Path(self.tmp.name) / "art")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_store_and_deduplicate_artwork(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
        p1 = self.cache.store(png, "image/png")
        p2 = self.cache.store(png, "image/png")
        self.assertIsNotNone(p1)
        self.assertEqual(p1, p2)
        assert p1 is not None
        self.assertTrue(Path(p1).exists())
        self.assertEqual(Path(p1).suffix, ".png")

    def test_malformed_artwork_returns_none(self) -> None:
        self.assertIsNone(self.cache.store(b"", "image/png"))
        self.assertIsNone(self.cache.store(None, "image/png"))  # type: ignore[arg-type]

    def test_resolve_missing(self) -> None:
        self.assertIsNone(self.cache.resolve(None))
        self.assertIsNone(self.cache.resolve(str(Path(self.tmp.name) / "nope.png")))


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "library.db")
        self.art = self.dir / "artwork"
        self.art.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recursive_scan_and_import(self) -> None:
        write_wav(self.dir / "a.wav")
        write_wav(self.dir / "sub" / "b.wav")
        (self.dir / "sub" / "note.txt").write_text("ignore")
        worker = MusicScannerWorker(db_path=self.db.db_path, artwork_dir=self.art)
        events = []
        worker.progress.connect(lambda *args: events.append(args))
        worker.scan([self.dir])
        self.assertEqual(self.db.track_count(), 2)
        self.assertTrue(events)

    def test_unreadable_and_missing_files_handled(self) -> None:
        write_wav(self.dir / "ok.wav")
        missing = self.dir / "missing.wav"
        worker = MusicScannerWorker(db_path=self.db.db_path, artwork_dir=self.art)
        worker.scan([self.dir / "ok.wav", missing])
        # ok imported, missing causes failed count
        self.assertEqual(self.db.track_count(), 1)

    def test_duplicate_scan_skips_unchanged(self) -> None:
        write_wav(self.dir / "same.wav")
        worker = MusicScannerWorker(db_path=self.db.db_path, artwork_dir=self.art)
        worker.scan([self.dir])
        self.assertEqual(self.db.track_count(), 1)
        # second scan should skip unchanged
        worker2 = MusicScannerWorker(db_path=self.db.db_path, artwork_dir=self.art)
        results = {}
        worker2.finished.connect(lambda d, i, s, f, c: results.update(dict(d=d, i=i, s=s, f=f, c=c)))
        worker2.scan([self.dir])
        self.assertEqual(self.db.track_count(), 1)
        self.assertEqual(results.get("i"), 0)
        self.assertEqual(results.get("s"), 1)

    def test_background_scanning_with_qthread(self) -> None:
        write_wav(self.dir / "bg.wav")
        thread = QThread()
        worker = MusicScannerWorker(db_path=self.db.db_path, artwork_dir=self.art)
        worker.set_paths([self.dir])
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        results = {}
        worker.finished.connect(lambda *args: results.setdefault("done", args))
        thread.start()
        self.assertTrue(wait_until(lambda: "done" in results, timeout=10.0))
        thread.quit()
        thread.wait(5000)
        worker.deleteLater()
        thread.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(self.db.track_count(), 1)
        self.assertFalse(results["done"][4])  # not cancelled


class IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "library.db")
        self.engine = AudioEngine()

    def tearDown(self) -> None:
        self.engine.stop()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        pump()
        self.tmp.cleanup()

    def test_library_to_audio_engine_integration(self) -> None:
        wav = write_wav(self.dir / "play.wav", seconds=1.0)
        self.db.add_track(make_track(str(wav), title="Play", artist="A", album="B", format="wav", duration=1000, file_size=wav.stat().st_size, file_mtime_ns=wav.stat().st_mtime_ns))
        track = self.db.get_track_by_path(wav)
        assert track is not None
        self.assertTrue(self.engine.open_files([track.file_path], autoplay=False))
        self.assertIsNotNone(self.engine.current_track)
        assert self.engine.current_track is not None
        self.assertEqual(Path(self.engine.current_track.path), wav.resolve())


if __name__ == "__main__":
    unittest.main(verbosity=2)
