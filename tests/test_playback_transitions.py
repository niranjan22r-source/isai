"""Tests for smooth Next/Previous track transitions."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEventLoop, QSettings, QTimer
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

from services.audio_engine import AudioEngine  # noqa: E402
from services.equalizer import EqualizerService  # noqa: E402


def _make_wav(path: Path, seconds: float = 2.0, freq: int = 440) -> None:
    import math, struct, wave
    sr = 44100
    n = int(sr * seconds)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i in range(n):
            v = int(12000 * math.sin(2 * math.pi * freq * (i / sr)))
            w.writeframes(struct.pack("<h", v))


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.paths = []
        for i, f in enumerate([440, 660, 880]):
            p = self.dir / f"t{i}.wav"
            _make_wav(p, seconds=3.0, freq=f)
            self.paths.append(p)
        settings = QSettings(str(self.dir / "s.ini"), QSettings.Format.IniFormat)
        self.eq = EqualizerService(settings)
        self.engine = AudioEngine(eq_service=self.eq)
        self.engine.open_files(self.paths, autoplay=False)

    def tearDown(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        self.engine.deleteLater()
        _pump(50)
        self.tmp.cleanup()

    def test_next_while_playing_starts_fade_out(self):
        self.engine.play()
        _pump(300)
        self.assertEqual(self.engine._state, "playing")
        self.engine.next_track()
        self.assertEqual(self.engine._transition_state, "fading_out")
        # track_changed should happen after fade-out, not immediately
        self.assertEqual(self.engine.current_track.path.resolve(), self.paths[0].resolve())

    def test_fade_out_completes_and_loads_track(self):
        self.engine.play()
        _pump(300)
        self.engine.next_track()
        _pump(500)  # > 200ms fade-out + load
        self.assertEqual(self.engine.current_track.path.resolve(), self.paths[1].resolve())

    def test_fade_in_reaches_full_gain(self):
        self.engine.play()
        _pump(300)
        self.engine.next_track()
        _pump(800)  # fade-out + fade-in
        self.assertEqual(self.engine._transition_gain, 1.0)
        self.assertEqual(self.engine._transition_state, "idle")

    def test_master_volume_preserved(self):
        self.engine.set_volume(55)
        self.engine.play()
        _pump(300)
        self.engine.next_track()
        _pump(800)
        self.assertEqual(self.engine.volume, 55)

    def test_rapid_next_latest_wins(self):
        self.engine.play()
        _pump(300)
        self.engine.next_track()
        self.engine.next_track()
        self.engine.next_track()  # should wrap/advance; queue has 3 tracks
        _pump(800)
        # Latest request wins - exact track depends on queue, but should be stable and gain restored.
        self.assertEqual(self.engine._transition_gain, 1.0)
        self.assertIn(self.engine._transition_state, ("idle", "fading_in"))

    def test_paused_track_change_is_immediate(self):
        self.engine.play()
        _pump(200)
        self.engine.pause()
        _pump(100)
        self.engine.next_track()
        _pump(50)
        self.assertEqual(self.engine.current_track.path.resolve(), self.paths[1].resolve())

    def test_transition_cancel_on_stop(self):
        self.engine.play()
        _pump(300)
        self.engine.next_track()
        self.assertEqual(self.engine._transition_state, "fading_out")
        self.engine.stop()
        self.assertEqual(self.engine._transition_state, "idle")
        self.assertEqual(self.engine._transition_gain, 1.0)


if __name__ == "__main__":
    unittest.main()
