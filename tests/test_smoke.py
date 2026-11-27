"""Smoke tests for the ISAI Session 1 foundation.

Run with:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Keep the GUI tests headless and independent of the desktop session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import main
from services.library_database import LibraryDatabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


class TestEnvironment(unittest.TestCase):
    def test_pyside6_imports(self) -> None:
        import PySide6
        from PySide6 import QtCore, QtWidgets

        self.assertTrue(PySide6.__version__)
        self.assertTrue(QtCore.qVersion())
        self.assertIsNotNone(QtWidgets.QMainWindow)

    def test_qt_multimedia_imports(self) -> None:
        from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

        device_descriptions = [
            device.description() for device in QMediaDevices.audioOutputs()
        ]
        self.assertIsInstance(device_descriptions, list)

        # Constructing the playback objects proves the multimedia plugin loads.
        player = QMediaPlayer()
        audio_output = QAudioOutput()
        player.setAudioOutput(audio_output)
        self.assertIsNotNone(player)
        player.deleteLater()
        audio_output.deleteLater()


class TestProjectStructure(unittest.TestCase):
    def test_required_paths_exist(self) -> None:
        required = [
            "main.py",
            "requirements.txt",
            "README.md",
            "DEVELOPMENT_LOG.md",
            ".gitignore",
            "core/__init__.py",
            "core/theme_manager.py",
            "ui/__init__.py",
            "ui/main_window.py",
            "ui/sidebar.py",
            "ui/player_bar.py",
            "ui/icons.py",
            "ui/components/__init__.py",
            "ui/pages/__init__.py",
            "services/__init__.py",
            "services/audio_engine.py",
            "services/library_database.py",
            "services/music_scanner.py",
            "services/metadata_reader.py",
            "services/artwork_cache.py",
            "assets/icons",
            "assets/images",
            "assets/fonts",
            "assets/styles",
            "data/cache",
            "tests",
        ]
        missing = [path for path in required if not (PROJECT_ROOT / path).exists()]
        self.assertEqual(missing, [], f"Missing project paths: {missing}")


class TestMainWindow(unittest.TestCase):
    def test_window_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = LibraryDatabase(Path(tmp) / "library.db")
            window = main.MainWindow(library_db=db)
            try:
                self.assertEqual(window.windowTitle(), "ISAI Music Player")
                self.assertEqual(window.size().width(), 1200)
                self.assertEqual(window.size().height(), 760)
                self.assertEqual(window.minimumWidth(), 850)
                self.assertEqual(window.minimumHeight(), 550)
                self.assertIsNotNone(window.centralWidget())
                self.assertIsNotNone(window.sidebar)
                self.assertIsNotNone(window.player_bar)
            finally:
                window.close()

    def test_application_starts_and_stops(self) -> None:
        assert _app is not None
        self.assertTrue(_app.quitOnLastWindowClosed())

        with tempfile.TemporaryDirectory() as tmp:
            db = LibraryDatabase(Path(tmp) / "library.db")
            window = main.MainWindow(library_db=db)
            window.show()
            QTimer.singleShot(100, _app.quit)
            exit_code = _app.exec()
            window.close()

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
