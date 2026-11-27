"""Session 5 UI enhancement tests."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QLabel

import main
from core.theme_manager import DARK, LIGHT, ThemeManager
from services.library_database import LibraryDatabase
from ui.components.album_card import AlbumCard
from ui.components.artist_card import ArtistCard
from ui.components.track_info_dialog import TrackInfoDialog

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


def pump(delay: float = 0.01) -> None:
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


def write_wav(path: Path, seconds: float = 0.5, rate: int = 22050) -> Path:
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
        "artist": "Unknown Artist",
        "album": "Unknown Album",
        "album_artist": "Unknown Artist",
        "track_number": None,
        "disc_number": None,
        "genre": "",
        "year": None,
        "duration": 1000,
        "format": path.suffix.lower().lstrip("."),
        "bitrate": 128000,
        "file_size": path.stat().st_size if path.exists() else 100,
        "file_mtime_ns": path.stat().st_mtime_ns if path.exists() else 1,
        "date_added": "2026-01-01T00:00:00+00:00",
        "artwork_path": None,
    }
    base.update(overrides)
    return base


class Session5UITestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "library.db")
        from PySide6.QtCore import QSettings
        self.settings = QSettings(str(self.dir / "settings.ini"), QSettings.Format.IniFormat)
        self.theme = ThemeManager(self.settings)
        self.window = main.MainWindow(self.theme, library_db=self.db)
        self.window.show()
        pump()

    def tearDown(self) -> None:
        self.window.audio_engine.stop()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        pump()
        self.tmp.cleanup()

    def populate(self) -> dict:
        a1 = write_wav(self.dir / "alpha.wav")
        a2 = write_wav(self.dir / "beta.wav")
        a3 = write_wav(self.dir / "gamma.wav")
        self.db.add_track(make_track(a1, title="Alpha Song", artist="Artist One", album="Album X", album_artist="Artist One", track_number=2, duration=2000, date_added="2026-01-01T00:00:00+00:00"))
        self.db.add_track(make_track(a2, title="Beta Song", artist="Artist Two", album="Album X", album_artist="Artist One", track_number=1, duration=3000, date_added="2026-01-02T00:00:00+00:00"))
        self.db.add_track(make_track(a3, title="Gamma Song", artist="Artist One", album="Album Y", album_artist="Artist One", track_number=1, duration=1000, date_added="2026-01-03T00:00:00+00:00"))
        self.window.refresh_library_views()
        return {"a1": a1, "a2": a2, "a3": a3}


class TestSongsPage(Session5UITestCase):
    def test_track_display_and_columns(self) -> None:
        self.populate()
        page = self.window.pages["songs"]
        self.assertEqual(page.table.columnCount(), 6)
        headers = [page.table.horizontalHeaderItem(i).text() for i in range(6)]
        self.assertEqual(headers, ["#", "Title", "Artist", "Album", "Duration", "Format"])
        self.assertEqual(page.table.rowCount(), 3)
        self.assertEqual(page.count_label.text(), "3 songs")

    def test_search_by_title_artist_album(self) -> None:
        self.populate()
        page = self.window.pages["songs"]
        page.search_field.setText("Alpha")
        page.refresh_library()
        self.assertEqual(page.table.rowCount(), 1)
        self.assertIn("matching", page.count_label.text())
        page.search_field.setText("Artist Two")
        page.refresh_library()
        self.assertEqual(page.table.rowCount(), 1)
        page.search_field.setText("Album Y")
        page.refresh_library()
        self.assertEqual(page.table.rowCount(), 1)

    def test_empty_search_results(self) -> None:
        self.populate()
        self.window.navigate("songs")
        page = self.window.pages["songs"]
        page.search_field.setText("zzzz-nope")
        page.refresh_library()
        self.assertEqual(page.table.rowCount(), 0)
        self.assertTrue(page.empty_state.isVisible())
        self.assertEqual(page.empty_state.title_label.text(), "No matching songs")

    def test_sorting_and_direction(self) -> None:
        self.populate()
        page = self.window.pages["songs"]
        page.sort_combo.setCurrentText("Duration")
        page.refresh_library()
        durations = [page.table.item(r, 4).text() for r in range(page.table.rowCount())]
        self.assertEqual(durations, sorted(durations))
        page._toggle_sort_direction()
        durations_desc = [page.table.item(r, 4).text() for r in range(page.table.rowCount())]
        self.assertEqual(durations_desc, list(reversed(durations)))

    def test_selection_and_double_click_playback(self) -> None:
        paths = self.populate()
        page = self.window.pages["songs"]
        self.window.navigate("songs")
        page.table.selectRow(0)
        tracks = page._selected_tracks()
        self.assertEqual(len(tracks), 1)
        # Double click integration: play selected track via engine.
        page._play_tracks(tracks)
        self.assertIsNotNone(self.window.audio_engine.current_track)
        assert self.window.audio_engine.current_track is not None
        self.assertTrue(str(self.window.audio_engine.current_track.path))

    def test_track_information_dialog(self) -> None:
        self.populate()
        track = self.db.get_all_tracks()[0]
        dialog = TrackInfoDialog(track, self.window)
        self.assertEqual(dialog.windowTitle(), "Track Information")
        texts = [w.text() for w in dialog.findChildren(QLabel)]
        self.assertTrue(any(track.title in t for t in texts))
        self.assertTrue(any(track.file_path in t for t in texts))
        dialog.close()


class TestAlbumsPage(Session5UITestCase):
    def test_album_grouping_and_cards(self) -> None:
        self.populate()
        page = self.window.pages["albums"]
        self.window.refresh_library_views()
        cards = page.findChildren(AlbumCard)
        self.assertEqual(len(cards), 2)  # Album X and Album Y

    def test_album_search_and_sort(self) -> None:
        self.populate()
        page = self.window.pages["albums"]
        page.search_field.setText("Album Y")
        page.refresh_library()
        self.assertEqual(len(page.album_grid.findChildren(AlbumCard)), 1)
        page.search_field.clear()
        page.refresh_library()
        page.sort_combo.setCurrentText("Track count")
        page.refresh_library()
        self.assertIn("2 albums", page.count_label.text())

    def test_album_navigation_and_track_ordering(self) -> None:
        self.populate()
        self.window.navigate("albums")
        page = self.window.pages["albums"]
        page.refresh_library()
        # Find Album X card
        card = None
        for c in page.findChildren(AlbumCard):
            if c.payload and c.payload.get("album") == "Album X":
                card = c
                break
        self.assertIsNotNone(card)
        assert card is not None
        page._show_album_detail(card)
        self.assertTrue(page.detail_container.isVisible())
        self.assertEqual(page.detail_table.rowCount(), 2)
        # Track 1 (Beta) should come before Track 2 (Alpha) in Album X
        self.assertEqual(page.detail_table.item(0, 1).text(), "Beta Song")
        self.assertEqual(page.detail_table.item(1, 1).text(), "Alpha Song")


class TestArtistsPage(Session5UITestCase):
    def test_artist_grouping_counts(self) -> None:
        self.populate()
        page = self.window.pages["artists"]
        page.refresh_library()
        cards = page.findChildren(ArtistCard)
        self.assertEqual(len(cards), 2)
        # Find Artist One
        a1 = next(c for c in cards if c._name == "Artist One")
        self.assertIn("2 albums", a1.subtitle_label.toolTip())
        self.assertIn("2 tracks", a1.subtitle_label.toolTip())

    def test_artist_search_sort_and_long_names(self) -> None:
        long_name = "A Very Very Very Long Artist Name That Should Be Elided Properly"
        p = write_wav(self.dir / "long.wav")
        self.db.add_track(make_track(p, title="Long", artist=long_name, album="A", album_artist=long_name))
        self.window.refresh_library_views()
        page = self.window.pages["artists"]
        page.search_field.setText("Very Very")
        page.refresh_library()
        cards = page.findChildren(ArtistCard)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]._name, long_name)
        # label should be elided (not equal to full name when width constrained)
        self.assertTrue(cards[0].name_label.toolTip() == long_name)

    def test_artist_navigation(self) -> None:
        self.populate()
        page = self.window.pages["artists"]
        page.refresh_library()
        card = next(c for c in page.findChildren(ArtistCard) if c._name == "Artist Two")
        page._open_artist(card)
        self.assertEqual(self.window.current_page_key, "songs")
        songs = self.window.pages["songs"]
        self.assertEqual(songs.search_field.text(), "Artist Two")


class TestGeneralUI(Session5UITestCase):
    def test_theme_switching(self) -> None:
        assert _app is not None
        self.theme.set_theme(DARK)
        pump()
        self.theme.set_theme(LIGHT)
        pump()
        self.assertEqual(self.theme.theme, LIGHT)
        self.theme.set_theme(DARK)
        self.assertEqual(self.theme.theme, DARK)

    def test_window_resizing(self) -> None:
        self.window.resize(900, 600)
        pump()
        self.assertTrue(self.window.sidebar.is_collapsed)
        self.window.resize(1200, 760)
        pump()
        self.assertFalse(self.window.sidebar.is_collapsed)

    def test_navigation_and_playback_continuity(self) -> None:
        paths = self.populate()
        page = self.window.pages["songs"]
        track = self.db.get_all_tracks()[0]
        self.window.audio_engine.open_files([track.file_path], autoplay=False)
        self.assertIsNotNone(self.window.audio_engine.current_track)
        for key in ["albums", "artists", "home", "songs", "settings"]:
            self.window.navigate(key)
            pump()
            self.assertEqual(self.window.current_page_key, key)
            self.assertIsNotNone(self.window.audio_engine.current_track)

    def test_artwork_placeholder_behavior(self) -> None:
        self.populate()
        page = self.window.pages["albums"]
        page.refresh_library()
        cards = page.findChildren(AlbumCard)
        self.assertTrue(cards)
        # No artwork paths set - should still render without crash
        for card in cards:
            card.refresh_theme(self.theme.colors)
            self.assertFalse(card.art_label.pixmap().isNull())


if __name__ == "__main__":
    unittest.main(verbosity=2)
