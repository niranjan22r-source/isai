"""UI tests for the ISAI Session 2 interface shell."""

from __future__ import annotations

import math
import os
import struct
import tempfile
import time
import unittest
import wave
from unittest.mock import patch

# Keep GUI tests headless and independent of the desktop session.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel

import main
from core import __version__
from core.theme_manager import DARK, LIGHT, THEMES, THEME_SETTINGS_KEY, ThemeManager
from services.audio_engine import STATE_PAUSED, STATE_PLAYING, AudioEngine
from services.library_database import LibraryDatabase
from ui.components.album_card import AlbumCard
from ui.components.artist_card import ArtistCard
from ui.components.empty_state import EmptyState
from ui.components.section_header import SectionHeader
from ui.icons import available_icons, icon
from ui.sidebar import COLLAPSED_WIDTH, EXPANDED_WIDTH

PAGE_KEYS = [
    "home",
    "now_playing",
    "songs",
    "albums",
    "artists",
    "playlists",
    "favorites",
    "recent",
    "equalizer",
    "settings",
]

_app: QApplication | None = None


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


def write_tone(path, seconds: float = 2.0, rate: int = 44100) -> None:
    frames = bytearray()
    for index in range(int(rate * seconds)):
        sample = int(9000 * math.sin(2.0 * math.pi * 440.0 * index / rate))
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


class UITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings_path = os.path.join(self._tmp.name, "settings.ini")
        self.settings = QSettings(
            self.settings_path, QSettings.Format.IniFormat
        )
        self.manager = ThemeManager(self.settings)
        self.db = LibraryDatabase(os.path.join(self._tmp.name, "library.db"))
        self.window = main.MainWindow(self.manager, library_db=self.db)

    def tearDown(self) -> None:
        self.window.audio_engine.stop()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert _app is not None
        _app.processEvents()
        self._tmp.cleanup()


class TestWindow(UITestCase):
    def test_defaults_and_minimum_size(self) -> None:
        self.assertEqual(self.window.windowTitle(), "ISAI Music Player")
        self.assertEqual(self.window.size().width(), 1200)
        self.assertEqual(self.window.size().height(), 760)
        self.assertEqual(self.window.minimumWidth(), 850)
        self.assertEqual(self.window.minimumHeight(), 550)

    def test_all_pages_are_created(self) -> None:
        self.assertEqual(list(self.window.pages), PAGE_KEYS)
        self.assertEqual(self.window.page_stack.count(), len(PAGE_KEYS))
        self.assertEqual(self.window.current_page_key, "home")
        self.assertIs(self.window.current_page, self.window.pages["home"])

    def test_page_headings(self) -> None:
        expected = {
            "home": "Welcome to ISAI",
            "now_playing": "Now Playing",
            "songs": "Songs",
            "albums": "Albums",
            "artists": "Artists",
            "playlists": "Playlists",
            "favorites": "Favorites",
            "recent": "Recently Played",
            "equalizer": "Equalizer",
            "settings": "Settings",
        }
        for key, title in expected.items():
            self.assertEqual(
                self.window.pages[key].header.title_label.text(), title
            )

    def test_player_bar_is_outside_the_page_stack(self) -> None:
        self.assertEqual(self.window.page_stack.indexOf(self.window.player_bar), -1)
        self.window.show()
        assert _app is not None
        _app.processEvents()
        self.assertTrue(self.window.player_bar.isVisible())

    def test_player_bar_no_track_state(self) -> None:
        player = self.window.player_bar
        self.assertEqual(player.track_title.text(), "No track playing")
        self.assertTrue(player.track_artist.text())
        for control in (
            player.favorite_button,
            player.previous_button,
            player.play_button,
            player.next_button,
        ):
            self.assertFalse(control.isEnabled())
        self.assertTrue(player.queue_button.isEnabled())
        self.assertTrue(player.shuffle_button.isEnabled())
        self.assertTrue(player.repeat_button.isEnabled())
        self.assertFalse(player.progress_slider.isEnabled())
        self.assertTrue(player.volume_slider.isEnabled())
        self.assertTrue(player.volume_button.isEnabled())
        self.assertEqual(player.progress_slider.value(), 0)
        self.assertEqual(player.current_time.text(), "0:00")
        self.assertEqual(player.duration_time.text(), "0:00")
        self.assertEqual(player.volume_slider.value(), 70)

    def test_audio_engine_is_wired_to_the_player_bar(self) -> None:
        self.assertIsInstance(self.window.audio_engine, AudioEngine)
        self.assertIs(self.window.player_bar._engine, self.window.audio_engine)
        self.assertEqual(self.window.audio_engine.volume, 70)
        self.assertFalse(self.window.audio_engine.muted)

    def test_file_menu_offers_open_and_quit(self) -> None:
        actions = []
        for menu_action in self.window.menuBar().actions():
            menu = menu_action.menu()
            if menu is not None:
                actions.extend(menu.actions())
        texts = [action.text() for action in actions]
        self.assertIn("&Open Audio Files…", texts)
        self.assertIn("&Quit", texts)
        self.assertIsNotNone(self.window.open_action.shortcut())


class TestPlayerBarIntegration(UITestCase):
    def _load_tone(self, seconds: float = 2.0) -> str:
        path = os.path.join(self._tmp.name, "UI Tone.wav")
        write_tone(path, seconds=seconds)
        self.assertTrue(self.window.load_audio_files([path], autoplay=False))
        self.assertTrue(
            wait_until(lambda: self.window.audio_engine.duration > 0),
            "Qt Multimedia did not report a duration for the generated WAV.",
        )
        return path

    def test_track_metadata_and_control_states_update(self) -> None:
        self._load_tone()
        player = self.window.player_bar
        engine = self.window.audio_engine

        self.assertEqual(player.track_title.text(), "UI Tone")
        self.assertEqual(player.track_artist.text(), "Unknown artist")
        self.assertTrue(player.play_button.isEnabled())
        self.assertTrue(player.previous_button.isEnabled())
        self.assertFalse(player.next_button.isEnabled())
        self.assertTrue(player.progress_slider.isEnabled())
        self.assertEqual(player.progress_slider.maximum(), engine.duration)
        self.assertEqual(player.duration_time.text(), "0:02")

        # Queue is available; favorite requires library track.
        self.assertTrue(player.queue_button.isEnabled())
        self.assertFalse(player.favorite_button.isEnabled())
        self.assertTrue(player.shuffle_button.isEnabled())
        self.assertTrue(player.repeat_button.isEnabled())

    def test_play_pause_tooltip_and_progress(self) -> None:
        engine = self.window.audio_engine
        if not engine.audio_output_available:
            self.skipTest("No audio output device is available in this session.")
        engine.set_volume(0)  # Keep automated playback silent.
        self._load_tone(seconds=3.0)
        player = self.window.player_bar

        player.play_button.click()
        self.assertTrue(
            wait_until(lambda: engine.playback_state == STATE_PLAYING)
        )
        self.assertEqual(player.play_button.toolTip(), "Pause (Space)")
        self.assertTrue(wait_until(lambda: engine.position >= 1000))
        self.assertGreater(player.progress_slider.value(), 0)
        self.assertEqual(player.current_time.text(), "0:01")

        player.play_button.click()
        self.assertTrue(
            wait_until(lambda: engine.playback_state == STATE_PAUSED)
        )
        self.assertEqual(player.play_button.toolTip(), "Play (Space)")

    def test_drag_to_seek_updates_the_engine(self) -> None:
        self._load_tone(seconds=3.0)
        player = self.window.player_bar
        engine = self.window.audio_engine

        player.progress_slider.sliderPressed.emit()
        player.progress_slider.setValue(1500)
        player.progress_slider.sliderMoved.emit(1500)
        self.assertEqual(player.current_time.text(), "0:01")

        player.progress_slider.sliderReleased.emit()
        self.assertTrue(wait_until(lambda: engine.position >= 1400))
        self.assertEqual(player.current_time.text(), "0:01")

    def test_volume_and_mute_controls_drive_the_engine(self) -> None:
        player = self.window.player_bar
        engine = self.window.audio_engine

        player.volume_slider.setValue(35)
        self.assertEqual(engine.volume, 35)

        player.volume_button.click()
        self.assertTrue(engine.muted)
        self.assertEqual(player.volume_button.toolTip(), "Unmute (Ctrl+M)")

        player.volume_button.click()
        self.assertFalse(engine.muted)
        self.assertEqual(player.volume_button.toolTip(), "Mute (Ctrl+M)")

    def test_open_dialog_selection_loads_and_plays(self) -> None:
        path = os.path.join(self._tmp.name, "Dialog Tone.wav")
        write_tone(path, seconds=1.0)
        self.window.audio_engine.set_volume(0)  # Keep automated playback silent.

        with patch.object(
            QFileDialog, "getOpenFileNames", return_value=([path], "")
        ):
            self.window.open_audio_files()

        self.assertTrue(
            wait_until(lambda: self.window.audio_engine.duration > 0)
        )
        self.assertEqual(self.window.player_bar.track_title.text(), "Dialog Tone")


class TestNavigation(UITestCase):
    def test_sidebar_clicks_switch_pages_and_keep_player_bar(self) -> None:
        self.window.show()
        assert _app is not None
        _app.processEvents()

        for key in PAGE_KEYS:
            self.window.sidebar.item(key).click()
            _app.processEvents()
            self.assertEqual(self.window.current_page_key, key)
            self.assertIs(self.window.current_page, self.window.pages[key])
            self.assertTrue(self.window.sidebar.item(key).isChecked())
            self.assertTrue(self.window.player_bar.isVisible())

        checked = [
            key
            for key in PAGE_KEYS
            if self.window.sidebar.item(key).isChecked()
        ]
        self.assertEqual(checked, ["settings"])

    def test_home_section_actions_navigate(self) -> None:
        self.window.show()
        assert _app is not None
        _app.processEvents()

        home = self.window.pages["home"]
        headers = home.findChildren(SectionHeader)
        self.assertEqual(len(headers), 3)

        for header, target in zip(headers, ("recent", "songs", "favorites")):
            self.assertIsNotNone(header.action_button)
            header.action_button.click()
            _app.processEvents()
            self.assertEqual(self.window.current_page_key, target)
            self.window.navigate("home")


class TestSidebar(UITestCase):
    def test_manual_collapse_and_expand(self) -> None:
        self.window.show()
        assert _app is not None
        _app.processEvents()

        sidebar = self.window.sidebar
        self.assertFalse(sidebar.is_collapsed)
        self.assertEqual(sidebar.width(), EXPANDED_WIDTH)

        sidebar.toggle_button.click()
        _app.processEvents()
        self.assertTrue(sidebar.is_collapsed)
        self.assertEqual(sidebar.width(), COLLAPSED_WIDTH)
        self.assertEqual(sidebar.toggle_button.text(), "")
        self.assertEqual(sidebar.toggle_button.toolTip(), "Expand sidebar")
        self.assertFalse(sidebar.wordmark_label.isVisible())

        for key in PAGE_KEYS:
            item = sidebar.item(key)
            self.assertEqual(item.text(), "")
            self.assertFalse(item.icon().isNull())

        sidebar.toggle_button.click()
        _app.processEvents()
        self.assertFalse(sidebar.is_collapsed)
        self.assertEqual(sidebar.width(), EXPANDED_WIDTH)
        self.assertEqual(sidebar.item("songs").text(), "Songs")

    def test_auto_collapse_at_narrow_width(self) -> None:
        self.window.show()
        assert _app is not None
        _app.processEvents()

        self.window.resize(900, 600)
        _app.processEvents()
        self.assertTrue(self.window.sidebar.is_collapsed)
        self.assertEqual(self.window.sidebar.width(), COLLAPSED_WIDTH)

        self.window.resize(1200, 760)
        _app.processEvents()
        self.assertFalse(self.window.sidebar.is_collapsed)
        self.assertEqual(self.window.sidebar.width(), EXPANDED_WIDTH)


class TestThemes(UITestCase):
    def test_switch_applies_stylesheet_immediately(self) -> None:
        assert _app is not None
        self.assertEqual(self.manager.theme, DARK)
        self.assertIn(THEMES[DARK].bg, _app.styleSheet())

        self.manager.set_theme(LIGHT)
        self.assertEqual(self.manager.theme, LIGHT)
        self.assertIn(THEMES[LIGHT].bg, _app.styleSheet())
        self.assertIn(THEMES[LIGHT].accent, _app.styleSheet())

        self.manager.set_theme(DARK)
        self.assertEqual(self.manager.theme, DARK)
        self.assertIn(THEMES[DARK].bg, _app.styleSheet())

    def test_theme_is_persisted(self) -> None:
        self.manager.set_theme(LIGHT)
        self.assertEqual(self.settings.value(THEME_SETTINGS_KEY), LIGHT)

        reloaded = ThemeManager(
            QSettings(self.settings_path, QSettings.Format.IniFormat)
        )
        self.assertEqual(reloaded.theme, LIGHT)

    def test_saved_theme_is_applied_at_startup(self) -> None:
        self.manager.set_theme(LIGHT)

        reloaded = ThemeManager(
            QSettings(self.settings_path, QSettings.Format.IniFormat)
        )
        db = LibraryDatabase(os.path.join(self._tmp.name, "library2.db"))
        window = main.MainWindow(reloaded, library_db=db)
        try:
            assert _app is not None
            self.assertIn(THEMES[LIGHT].bg, _app.styleSheet())
            settings_page = window.pages["settings"]
            self.assertTrue(settings_page.theme_buttons[LIGHT].isChecked())
            self.assertEqual(settings_page.palette_name, "ISAI Light")
        finally:
            window.close()

    def test_invalid_theme_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.set_theme("neon")

    def test_settings_buttons_switch_theme(self) -> None:
        self.window.show()
        self.window.navigate("settings")
        assert _app is not None
        _app.processEvents()

        page = self.window.pages["settings"]
        self.assertTrue(page.theme_buttons[DARK].isChecked())

        page.theme_buttons[LIGHT].click()
        _app.processEvents()
        self.assertEqual(self.manager.theme, LIGHT)
        self.assertTrue(page.theme_buttons[LIGHT].isChecked())
        self.assertEqual(page.palette_name, "ISAI Light")
        self.assertEqual(self.settings.value(THEME_SETTINGS_KEY), LIGHT)


class TestContent(UITestCase):
    def test_empty_states_and_no_fake_library_data(self) -> None:
        for key in ("songs", "albums", "artists", "playlists", "favorites", "recent"):
            page = self.window.pages[key]
            self.assertGreaterEqual(len(page.findChildren(EmptyState)), 1, key)

        home = self.window.pages["home"]
        self.assertEqual(len(home.findChildren(EmptyState)), 3)

        self.assertEqual(len(self.window.pages["albums"].findChildren(AlbumCard)), 0)
        self.assertEqual(len(self.window.pages["artists"].findChildren(ArtistCard)), 0)

        playlists = self.window.pages["playlists"]
        self.assertTrue(playlists.create_playlist_button.isEnabled())

    def test_icons_render(self) -> None:
        for name in available_icons():
            self.assertFalse(icon(name, "#ffffff", 20).isNull(), name)

    def test_application_metadata(self) -> None:
        self.assertEqual(__version__, "0.9.0")
        settings_page = self.window.pages["settings"]
        texts = [label.text() for label in settings_page.findChildren(QLabel)]
        self.assertTrue(any(__version__ in text for text in texts))


if __name__ == "__main__":
    unittest.main(verbosity=2)
