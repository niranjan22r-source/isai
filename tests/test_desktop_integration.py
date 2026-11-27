"""Session 10 tests: MPRIS, notifications, tray, desktop settings."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtDBus import QDBusArgument, QDBusObjectPath, QDBusVariant
from PySide6.QtWidgets import QApplication

import main
from core.theme_manager import ThemeManager
from services.audio_engine import AudioEngine
from services.library_database import LibraryDatabase
from services.mpris_service import MprisService, MPRIS_PLAYER_IFACE
from services.notification_service import NotificationService

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


class MprisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.db = LibraryDatabase(os.path.join(self.dir, "lib.db"))
        self.engine = AudioEngine()
        self.mpris = MprisService(self.engine, self.db)

    def tearDown(self) -> None:
        try: self.engine.stop()
        except Exception: pass
        self.engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def test_metadata_and_status_defaults(self) -> None:
        self.assertEqual(self.mpris.playback_status(), "Stopped")
        md = self.mpris.metadata()
        self.assertIn("mpris:trackid", md)
        self.assertFalse(self.mpris.can_seek())

    def test_metadata_includes_length_and_album(self) -> None:
        from pathlib import Path
        from types import SimpleNamespace

        class _Track:
            path = Path("/tmp/song.mp3")
            title = "Song"
            artist = "Artist"
            album = "Album"

        engine = SimpleNamespace(
            queue_manager=SimpleNamespace(current_item=None),
            current_track=_Track(),
            duration=218331,
        )
        svc = MprisService(engine, None)
        md = svc.metadata()
        self.assertEqual(md["xesam:title"], "Song")
        self.assertEqual(md["xesam:artist"], ["Artist"])
        self.assertEqual(md["xesam:album"], "Album")
        self.assertEqual(md["mpris:length"], 218331000)
        self.assertEqual(md["xesam:url"], "file:///tmp/song.mp3")

    def test_commands_delegate_to_engine(self) -> None:
        # create a wav
        import wave, os
        path = os.path.join(self.dir, "t.wav")
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(22050)
            wf.writeframes(b"\x00\x00" * 22050)
        self.assertTrue(self.engine.open_files([path], autoplay=False))
        self.assertEqual(self.mpris.playback_status(), "Stopped")
        self.mpris.play()
        QCoreApplication.processEvents()
        # Can be Playing or Stopped depending on backend, but command should not crash.
        self.mpris.pause()
        self.mpris.play_pause()
        self.mpris.set_volume(0.5)
        self.assertEqual(self.engine.volume, 50)
        md = self.mpris.metadata()
        self.assertEqual(md["xesam:title"], "t")
        self.assertIsInstance(md["xesam:artist"], list)
        self.assertEqual(md["xesam:artist"], ["Unknown artist"])
        # Metadata values stay plain so QtDBus wraps them exactly once.
        self.assertNotIsInstance(md["xesam:title"], QDBusVariant)
        self.assertNotIsInstance(md["mpris:trackid"], QDBusVariant)

    def test_properties_changed_uses_plain_values(self) -> None:
        class _FakeBus:
            def __init__(self) -> None:
                self.messages = []

            def send(self, message) -> bool:
                self.messages.append(message)
                return True

        bus = _FakeBus()
        self.mpris._bus = bus
        self.mpris._registered = True
        self.mpris._emit_props(MPRIS_PLAYER_IFACE, ["Metadata", "PlaybackStatus"])
        self.assertEqual(len(bus.messages), 1)
        args = bus.messages[0].arguments()
        changed = args[1]
        self.assertIsInstance(changed["Metadata"], dict)
        self.assertIsInstance(changed["Metadata"]["mpris:trackid"], QDBusObjectPath)
        self.assertIsInstance(changed["PlaybackStatus"], str)
        # The third PropertiesChanged argument must be an explicitly typed
        # empty "as" array; a plain Python list is inferred as "av" and makes
        # GDBusProxy clients drop the whole signal.
        self.assertIsInstance(args[2], QDBusArgument)
        self.assertNotIsInstance(args[2], list)


class NotificationServiceTests(unittest.TestCase):
    def test_disabled_and_dedupe(self) -> None:
        n = NotificationService()
        n.set_enabled(False)
        self.assertFalse(n.notify_track("A", "B"))
        n.set_enabled(True)
        # If unavailable on bus, notify returns False; dedupe logic still safe.
        n._last_notified = "A\x00B\x00"
        self.assertFalse(n.notify_track("A", "B", ""))


class DesktopSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)
        self.theme = ThemeManager(self.settings)
        self.db = LibraryDatabase(os.path.join(self.tmp.name, "lib.db"))
        self.window = main.MainWindow(self.theme, library_db=self.db)
        self.window.show()

    def tearDown(self) -> None:
        try: self.window.audio_engine.stop()
        except Exception: pass
        self.window._quitting = True
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def test_notification_and_close_settings_persist(self) -> None:
        self.window.set_notifications_enabled(False)
        self.window.set_close_to_tray(False)
        w2 = main.MainWindow(ThemeManager(QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.Format.IniFormat)), library_db=self.db)
        try:
            self.assertFalse(w2.notifications_enabled)
            self.assertFalse(w2.close_to_tray)
        finally:
            w2._quitting = True
            w2.close()
            w2.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_quit_app_closes_window(self) -> None:
        self.window.quit_app()
        QCoreApplication.processEvents()
        self.assertTrue(self.window._quitting)
