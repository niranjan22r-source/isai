"""Equalizer service, DSP, and UI smoke tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtWidgets import QApplication

import main
from core.theme_manager import ThemeManager
from services.equalizer import (
    BUILTIN_PRESETS,
    EqualizerService,
    MAX_GAIN_DB,
    MIN_GAIN_DB,
)
from services.equalizer_dsp import create_state, get_lib
from services.library_database import LibraryDatabase

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or main.create_application([])


class EqualizerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.tmp.name) / "s.ini"), QSettings.Format.IniFormat)
        self.eq = EqualizerService(self.settings)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_default_state_and_presets(self) -> None:
        self.assertTrue(self.eq.state.enabled)
        self.assertEqual(self.eq.state.mode, "normal")
        self.assertEqual(self.eq.state.active_preset, "Flat")
        self.assertEqual(self.eq.state.bands, [0.0] * 10)
        for name in BUILTIN_PRESETS:
            self.assertIn(name, self.eq.presets())

    def test_band_and_preamp_clamped(self) -> None:
        self.eq.set_band(0, 999)
        self.eq.set_preamp(-999)
        self.assertEqual(self.eq.state.bands[0], MAX_GAIN_DB)
        self.assertEqual(self.eq.state.preamp_db, -12.0)

    def test_apply_preset(self) -> None:
        ok = self.eq.apply_preset("Bass Boost")
        self.assertTrue(ok)
        self.assertEqual(self.eq.state.active_preset, "Bass Boost")
        self.assertEqual(self.eq.state.bands[0], 5.0)

    def test_custom_preset_crud(self) -> None:
        self.eq.set_band(2, 3)
        self.eq.set_preamp(-2)
        self.assertTrue(self.eq.save_custom_preset("MyPreset"))
        self.assertIn("MyPreset", self.eq.presets())
        self.eq.apply_preset("Flat")
        self.assertTrue(self.eq.apply_preset("MyPreset"))
        self.assertEqual(self.eq.state.bands[2], 3.0)
        self.assertTrue(self.eq.rename_custom_preset("MyPreset", "Renamed"))
        self.assertIn("Renamed", self.eq.presets())
        self.assertNotIn("MyPreset", self.eq.presets())
        self.assertTrue(self.eq.delete_custom_preset("Renamed"))
        self.assertNotIn("Renamed", self.eq.presets())

    def test_builtin_presets_protected(self) -> None:
        self.assertFalse(self.eq.save_custom_preset("Flat"))
        self.assertFalse(self.eq.delete_custom_preset("Rock"))
        self.assertFalse(self.eq.rename_custom_preset("Rock", "Stone"))

    def test_persistence(self) -> None:
        self.eq.set_mode("advanced")
        self.eq.set_enabled(False)
        self.eq.set_preamp(-3)
        self.eq.set_band(4, 6)
        self.eq.save_custom_preset("Mine")
        self.eq.apply_preset("Mine")
        eq2 = EqualizerService(self.settings)
        self.assertEqual(eq2.state.mode, "advanced")
        self.assertFalse(eq2.state.enabled)
        self.assertEqual(eq2.state.preamp_db, -3.0)
        self.assertEqual(eq2.state.bands[4], 6.0)
        self.assertIn("Mine", eq2.presets())


class EqualizerDspTests(unittest.TestCase):
    def test_dsp_processes_without_crash(self) -> None:
        import ctypes
        lib = get_lib()
        st = create_state()
        lib.eq_configure(ctypes.byref(st), 44100, 10,
                         (ctypes.c_double * 10)(*[31,62,125,250,500,1000,2000,4000,8000,16000]),
                         (ctypes.c_double * 10)(*[3,0,0,0,0,0,0,0,0,-3]),
                         (ctypes.c_double * 10)(*[1.0]*10), -2.0)
        buf = (ctypes.c_float * 200)()
        for i in range(200):
            buf[i] = 0.1 if i % 2 == 0 else -0.1
        lib.eq_process_f32(ctypes.byref(st), buf, 100)
        self.assertTrue(any(abs(buf[i]) > 0.0001 for i in range(200)))


class EqualizerUiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = LibraryDatabase(self.dir / "lib.db")
        self.settings = QSettings(str(self.dir / "s.ini"), QSettings.Format.IniFormat)
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
        QCoreApplication.processEvents()
        self.tmp.cleanup()

    def test_equalizer_page_navigation_and_mode(self) -> None:
        self.window.navigate("equalizer")
        page = self.window.pages["equalizer"]
        self.assertEqual(page._eq.state.mode, "normal")
        self.window.equalizer_service.set_mode("advanced")
        QCoreApplication.processEvents()
        self.assertTrue(page.advanced_card.isVisible())
        self.window.equalizer_service.set_mode("normal")
        QCoreApplication.processEvents()
        self.assertTrue(page.normal_card.isVisible())


if __name__ == "__main__":
    unittest.main(verbosity=2)
