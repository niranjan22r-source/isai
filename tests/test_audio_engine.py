"""Automated tests for the Session 3 audio engine.

Generated WAV files exercise real Qt Multimedia decoding and playback. These
tests verify the engine and its signals; they cannot confirm audible sound,
which is covered separately by a manual desktop playback check.
"""

from __future__ import annotations

import math
import os
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path

# Keep multimedia tests headless and independent of the desktop session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

import main
from services.audio_engine import (
    DEFAULT_VOLUME,
    STATE_PAUSED,
    STATE_PLAYING,
    STATE_STOPPED,
    SUPPORTED_EXTENSIONS,
    AudioEngine,
    TrackInfo,
)

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


def pump(delay: float = 0.005) -> None:
    assert _app is not None
    _app.processEvents()
    time.sleep(delay)


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        pump()
    return bool(predicate())


def write_tone(
    path: Path,
    seconds: float = 1.0,
    frequency: float = 440.0,
    rate: int = 44100,
    amplitude: int = 8000,
) -> Path:
    """Write a mono 16-bit PCM WAV tone with the standard library only."""
    frame_count = int(rate * seconds)
    frames = bytearray()
    for index in range(frame_count):
        sample = int(
            amplitude * math.sin(2.0 * math.pi * frequency * index / rate)
        )
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return path


class AudioEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.engine = AudioEngine()
        self.errors: list[str] = []
        self.engine.error_occurred.connect(self.errors.append)

    def tearDown(self) -> None:
        self.engine.stop()
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        pump()
        self._tmp.cleanup()

    def require_output(self) -> None:
        if not self.engine.audio_output_available:
            self.skipTest("No audio output device is available in this session.")

    def load_tone(self, name: str = "tone.wav", seconds: float = 1.0) -> Path:
        path = write_tone(self.directory / name, seconds=seconds)
        self.assertTrue(self.engine.open_files([path]))
        self.assertTrue(
            wait_until(lambda: self.engine.duration > 0),
            "Qt Multimedia did not report a duration for the generated WAV.",
        )
        return path


class TestConstructionAndState(AudioEngineTestCase):
    def test_initial_state(self) -> None:
        engine = self.engine
        self.assertEqual(engine.playback_state, STATE_STOPPED)
        self.assertEqual(engine.position, 0)
        self.assertEqual(engine.duration, 0)
        self.assertEqual(engine.volume, DEFAULT_VOLUME)
        self.assertFalse(engine.muted)
        self.assertFalse(engine.is_playing)
        self.assertIsNone(engine.current_track)
        self.assertEqual(engine.tracks, ())
        self.assertEqual(engine.current_index, -1)
        self.assertIsInstance(engine.audio_output_available, bool)

    def test_supported_extensions_cover_requested_formats(self) -> None:
        self.assertEqual(
            SUPPORTED_EXTENSIONS,
            {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
        )

    def test_track_info_falls_back_to_filename(self) -> None:
        path = Path("/music/My Song.mp3")
        info = TrackInfo.from_path(path)
        self.assertEqual(info.path, path)
        self.assertEqual(info.title, "My Song")
        self.assertEqual(info.artist, "Unknown artist")


class TestVolumeAndMute(AudioEngineTestCase):
    def test_volume_is_clamped_and_signalled(self) -> None:
        seen: list[int] = []
        self.engine.volume_changed.connect(seen.append)

        self.engine.set_volume(42)
        self.assertEqual(self.engine.volume, 42)
        self.engine.set_volume(150)
        self.assertEqual(self.engine.volume, 100)
        self.engine.set_volume(-10)
        self.assertEqual(self.engine.volume, 0)
        self.assertEqual(seen, [42, 100, 0])

        before = len(seen)
        self.engine.set_volume(0)
        self.assertEqual(len(seen), before)

    def test_mute_toggles_and_signals(self) -> None:
        seen: list[bool] = []
        self.engine.muted_changed.connect(seen.append)

        self.engine.toggle_mute()
        self.assertTrue(self.engine.muted)
        self.engine.toggle_mute()
        self.assertFalse(self.engine.muted)
        self.assertEqual(seen, [True, False])

        self.engine.set_muted(False)
        self.assertEqual(seen, [True, False])


class TestFileValidation(AudioEngineTestCase):
    def test_missing_and_unsupported_files_are_rejected(self) -> None:
        missing = self.directory / "missing.mp3"
        unsupported = self.directory / "notes.txt"
        unsupported.write_text("not audio", encoding="utf-8")

        opened = self.engine.open_files([missing, unsupported])

        self.assertFalse(opened)
        self.assertEqual(self.engine.tracks, ())
        self.assertIsNone(self.engine.current_track)
        self.assertTrue(self.errors)
        message = self.errors[-1].lower()
        self.assertIn("file not found", message)
        self.assertIn("unsupported format", message)

    def test_empty_selection_is_a_no_op(self) -> None:
        self.assertFalse(self.engine.open_files([]))
        self.assertEqual(self.engine.tracks, ())
        self.assertEqual(self.errors, [])

    def test_duplicate_paths_are_not_added_twice(self) -> None:
        path = self.load_tone()
        self.assertTrue(self.engine.open_files([path]))
        self.assertEqual(len(self.engine.tracks), 1)
        self.assertEqual(self.engine.current_index, 0)

    def test_valid_file_still_loads_when_another_is_skipped(self) -> None:
        valid = write_tone(self.directory / "valid.wav")
        missing = self.directory / "missing.mp3"

        self.assertTrue(self.engine.open_files([valid, missing]))
        self.assertIsNotNone(self.engine.current_track)
        self.assertEqual(self.engine.current_track.path, valid.resolve())
        self.assertTrue(self.errors)
        self.assertIn("file not found", self.errors[-1].lower())


class TestLoadingAndMetadata(AudioEngineTestCase):
    def test_wav_loads_with_duration_and_filename_metadata(self) -> None:
        tracks: list[TrackInfo | None] = []
        self.engine.track_changed.connect(tracks.append)
        path = self.load_tone("Opening Theme.wav", seconds=1.5)

        track = self.engine.current_track
        self.assertIsNotNone(track)
        assert track is not None
        self.assertEqual(track.path, path.resolve())
        self.assertEqual(track.title, "Opening Theme")
        self.assertEqual(track.artist, "Unknown artist")
        self.assertEqual(self.engine.tracks, (path.resolve(),))
        self.assertEqual(self.engine.current_index, 0)
        self.assertGreaterEqual(self.engine.duration, 1400)
        self.assertLessEqual(self.engine.duration, 1600)
        self.assertTrue(tracks)
        self.assertEqual(tracks[0].title, "Opening Theme")

    def test_invalid_audio_file_reports_an_error(self) -> None:
        broken = self.directory / "broken.mp3"
        broken.write_bytes(b"this is definitely not an audio stream")

        self.assertTrue(self.engine.open_files([broken], autoplay=True))
        self.assertTrue(
            wait_until(lambda: bool(self.errors), timeout=8.0),
            "No error was reported for an invalid audio file.",
        )
        message = self.errors[-1].lower()
        self.assertTrue(
            any(
                token in message
                for token in ("could not", "format", "playback", "output")
            ),
            self.errors[-1],
        )
        self.assertEqual(self.engine.playback_state, STATE_STOPPED)


class TestQueueNavigation(AudioEngineTestCase):
    def test_next_and_previous_walk_the_temporary_queue(self) -> None:
        first = write_tone(self.directory / "first.wav")
        second = write_tone(self.directory / "second.wav")

        self.assertTrue(self.engine.open_files([first, second]))
        self.assertEqual(self.engine.current_index, 0)
        self.assertEqual(self.engine.current_track.path, first.resolve())

        self.assertTrue(self.engine.next_track())
        self.assertEqual(self.engine.current_index, 1)
        self.assertEqual(self.engine.current_track.path, second.resolve())

        self.assertFalse(self.engine.next_track())
        self.assertEqual(self.engine.playback_state, STATE_STOPPED)

        self.assertTrue(self.engine.previous_track())
        self.assertEqual(self.engine.current_index, 0)
        self.assertEqual(self.engine.current_track.path, first.resolve())

        self.assertTrue(self.engine.previous_track())
        self.assertEqual(self.engine.position, 0)

    def test_navigation_without_tracks_reports_errors(self) -> None:
        self.assertFalse(self.engine.next_track())
        self.assertFalse(self.engine.previous_track())
        self.assertEqual(len(self.errors), 2)


class TestPlayback(AudioEngineTestCase):
    def test_play_pause_stop_and_position(self) -> None:
        self.require_output()
        self.engine.set_volume(0)  # Keep automated playback silent.
        path = write_tone(self.directory / "playback.wav", seconds=3.0)
        self.assertTrue(self.engine.open_files([path]))

        self.engine.play()
        self.assertTrue(
            wait_until(
                lambda: self.engine.playback_state == STATE_PLAYING,
                timeout=5.0,
            )
        )
        self.assertTrue(
            wait_until(lambda: self.engine.position > 150, timeout=5.0)
        )

        self.engine.pause()
        self.assertTrue(
            wait_until(
                lambda: self.engine.playback_state == STATE_PAUSED,
                timeout=5.0,
            )
        )
        paused_at = self.engine.position
        pump(0.25)
        self.assertLessEqual(abs(self.engine.position - paused_at), 200)

        self.engine.stop()
        self.assertEqual(self.engine.playback_state, STATE_STOPPED)
        self.assertEqual(self.engine.position, 0)

    def test_seek_and_clamping(self) -> None:
        self.require_output()
        self.engine.set_volume(0)  # Keep automated playback silent.
        path = write_tone(self.directory / "seek.wav", seconds=3.0)
        self.assertTrue(self.engine.open_files([path]))
        self.engine.play()
        self.assertTrue(
            wait_until(lambda: self.engine.position > 100, timeout=5.0)
        )

        self.engine.set_position(1500)
        self.assertTrue(
            wait_until(lambda: self.engine.position >= 1400, timeout=5.0)
        )

        self.engine.pause()
        wait_until(lambda: self.engine.playback_state == STATE_PAUSED)

        self.engine.set_position(-50)
        self.assertEqual(self.engine.position, 0)
        self.engine.set_position(self.engine.duration + 5000)
        self.assertEqual(self.engine.position, self.engine.duration)
        self.engine.stop()

    def test_play_without_a_track_reports_an_error(self) -> None:
        self.engine.play()
        self.assertTrue(self.errors)
        self.assertIn("no track", self.errors[-1].lower())
        self.assertEqual(self.engine.playback_state, STATE_STOPPED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
