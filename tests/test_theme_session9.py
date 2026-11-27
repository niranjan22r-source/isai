"""Session 9 tests: theme system, reduced motion, persistence."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication

import main
from core.theme_manager import DARK, LIGHT, SYSTEM, REDUCED_MOTION_KEY, THEME_SETTINGS_KEY, ThemeManager
from services.library_database import LibraryDatabase

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


class ThemeSession9Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_path = os.path.join(self.tmp.name, "settings.ini")
        self.settings = QSettings(self.settings_path, QSettings.Format.IniFormat)
        self.manager = ThemeManager(self.settings)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_reduced_motion_persisted(self) -> None:
        self.assertFalse(self.manager.reduced_motion)
        self.manager.set_reduced_motion(True)
        self.assertTrue(self.manager.reduced_motion)
        reloaded = ThemeManager(QSettings(self.settings_path, QSettings.Format.IniFormat))
        self.assertTrue(reloaded.reduced_motion)
        self.assertEqual(self.settings.value(REDUCED_MOTION_KEY), True)

    def test_system_theme_setting_persists(self) -> None:
        # System may or may not be supported; setting should be safe.
        self.manager.set_theme(SYSTEM)
        self.assertEqual(self.manager.theme, SYSTEM)
        reloaded = ThemeManager(QSettings(self.settings_path, QSettings.Format.IniFormat))
        self.assertEqual(reloaded.theme, SYSTEM)
        self.assertIn(reloaded.effective_theme, (DARK, LIGHT))

    def test_theme_switch_does_not_interrupt_playback(self) -> None:
        db = LibraryDatabase(os.path.join(self.tmp.name, "lib.db"))
        window = main.MainWindow(self.manager, library_db=db)
        try:
            window.show()
            # create a tiny wav
            wav = os.path.join(self.tmp.name, "t.wav")
            import wave
            with wave.open(wav, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
                wf.writeframes(b"\x00\x00" * 22050)
            self.assertTrue(window.audio_engine.open_files([wav], autoplay=False))
            state_before = window.audio_engine.playback_state
            self.manager.set_theme(LIGHT)
            QCoreApplication.processEvents()
            self.assertEqual(window.audio_engine.playback_state, state_before)
            self.assertIsNotNone(window.audio_engine.current_track)
        finally:
            window.audio_engine.stop()
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
