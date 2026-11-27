"""Dedicated Equalizer page with Normal and Advanced modes."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.theme_manager import ThemeColors, ThemeManager
from services.equalizer import (
    BAND_FREQUENCIES,
    BAND_LABELS,
    BUILTIN_PRESETS,
    MAX_GAIN_DB,
    MAX_PREAMP_DB,
    MIN_GAIN_DB,
    MIN_PREAMP_DB,
    EqualizerService,
)
from ui.pages.base_page import BasePage


class EqResponseWidget(QFrame):
    """Simple frequency response visualization."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("eqResponse")
        self.setMinimumHeight(160)
        self._bands: list[float] = [0.0] * 10
        self._preamp: float = 0.0
        self._colors: ThemeColors | None = None

    def set_values(self, bands: list[float], preamp: float, colors: ThemeColors | None = None) -> None:
        self._bands = list(bands)[:10] + [0.0] * max(0, 10 - len(bands))
        self._preamp = float(preamp)
        if colors is not None:
            self._colors = colors
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = self._colors
        bg = QColor(c.surface_alt if c else "#1a1e25")
        border = QColor(c.border if c else "#232830")
        accent = QColor(c.accent if c else "#3dba9c")
        muted = QColor(c.text_faint if c else "#6a7382")
        p.fillRect(self.rect(), bg)
        p.setPen(QPen(border, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

        r = self.rect().adjusted(18, 16, -18, -20)
        if r.width() <= 10 or r.height() <= 10:
            p.end()
            return
        # grid
        p.setPen(QPen(QColor(muted.red(), muted.green(), muted.blue(), 60), 1))
        for db in (-12, -6, 0, 6, 12):
            y = self._y_for_db(db, r)
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QPen(muted, 1))
            p.drawText(QRectF(2, y - 8, 14, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(db))
            p.setPen(QPen(QColor(muted.red(), muted.green(), muted.blue(), 60), 1))

        # curve points
        pts: list[QPointF] = []
        for i, db in enumerate(self._bands):
            x = r.left() + (r.width() * i / 9.0)
            y = self._y_for_db(db + self._preamp, r)
            pts.append(QPointF(x, y))
            # point
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawEllipse(pts[-1], 4, 4)
            # label
            p.setPen(QPen(muted, 1))
            p.drawText(QRectF(x - 16, r.bottom() + 2, 32, 16), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, BAND_LABELS[i])

        if len(pts) >= 2:
            path = QPainterPath(pts[0])
            for i in range(1, len(pts)):
                prev = pts[i - 1]
                cur = pts[i]
                midx = (prev.x() + cur.x()) / 2
                path.cubicTo(QPointF(midx, prev.y()), QPointF(midx, cur.y()), cur)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(accent, 2))
            p.drawPath(path)
        p.end()

    def _y_for_db(self, db: float, r: QRectF) -> float:
        db = max(MIN_GAIN_DB, min(MAX_GAIN_DB, float(db)))
        t = (MAX_GAIN_DB - db) / (MAX_GAIN_DB - MIN_GAIN_DB)
        return r.top() + t * r.height()


class EqualizerPage(BasePage):
    def __init__(self, theme_manager: ThemeManager, eq_service: EqualizerService, parent: QWidget | None = None) -> None:
        super().__init__("Equalizer", "Shape your sound.", parent=parent)
        self._theme = theme_manager
        self._eq = eq_service
        self._colors = theme_manager.colors
        self._band_sliders: list[QSlider] = []
        self._band_labels: list[QLabel] = []
        self._updating = False

        self._build_ui()
        self._eq.state_changed.connect(self._sync_from_state)
        self._eq.preset_changed.connect(lambda _n: self._sync_from_state())
        theme_manager.theme_changed.connect(lambda _t: self.refresh_theme(theme_manager.colors))
        self.refresh_theme(self._colors)
        self._sync_from_state()

    # ------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        top = QFrame(self)
        top.setObjectName("settingsCard")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(18, 14, 18, 14)
        top_l.setSpacing(12)

        self.enable_btn = QPushButton("Enabled", top)
        self.enable_btn.setCheckable(True)
        self.enable_btn.setObjectName("secondaryButton")
        self.enable_btn.clicked.connect(lambda checked: self._eq.set_enabled(checked))
        top_l.addWidget(self.enable_btn)

        top_l.addWidget(QLabel("Mode:", top))
        self.mode_combo = QComboBox(top)
        self.mode_combo.addItem("Normal", "normal")
        self.mode_combo.addItem("Advanced", "advanced")
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top_l.addWidget(self.mode_combo)

        top_l.addStretch(1)

        self.preset_combo = QComboBox(top)
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        top_l.addWidget(QLabel("Preset:", top))
        top_l.addWidget(self.preset_combo, 1)

        self.reset_btn = QPushButton("Reset to Flat", top)
        self.reset_btn.setObjectName("secondaryButton")
        self.reset_btn.clicked.connect(self._eq.reset_flat)
        top_l.addWidget(self.reset_btn)
        self.body.addWidget(top)

        # Normal mode card
        self.normal_card = QFrame(self)
        self.normal_card.setObjectName("settingsCard")
        n = QVBoxLayout(self.normal_card)
        n.setContentsMargins(18, 16, 18, 16)
        n.setSpacing(12)
        n.addWidget(self._title("Normal Mode"))
        n.addWidget(self._hint("Simple 10-band control with preamp and presets."))
        self.normal_bands_row = self._build_bands_row(self.normal_card, prefix="n")
        n.addWidget(self.normal_bands_row)
        self.normal_preamp = self._build_preamp_row(self.normal_card, prefix="n")
        n.addLayout(self.normal_preamp)
        self.body.addWidget(self.normal_card)

        # Advanced mode card
        self.advanced_card = QFrame(self)
        self.advanced_card.setObjectName("settingsCard")
        a = QVBoxLayout(self.advanced_card)
        a.setContentsMargins(18, 16, 18, 16)
        a.setSpacing(12)
        a.addWidget(self._title("Advanced Mode"))
        a.addWidget(self._hint("Detailed 10-band graphic EQ with response visualization and custom preset management."))
        self.response = EqResponseWidget(self.advanced_card)
        a.addWidget(self.response)
        self.advanced_bands_row = self._build_bands_row(self.advanced_card, prefix="a")
        a.addWidget(self.advanced_bands_row)
        self.advanced_preamp = self._build_preamp_row(self.advanced_card, prefix="a")
        a.addLayout(self.advanced_preamp)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self.save_preset_btn = QPushButton("Save as Preset", self.advanced_card)
        self.save_preset_btn.setObjectName("secondaryButton")
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.rename_preset_btn = QPushButton("Rename Preset", self.advanced_card)
        self.rename_preset_btn.setObjectName("secondaryButton")
        self.rename_preset_btn.clicked.connect(self._rename_preset)
        self.delete_preset_btn = QPushButton("Delete Preset", self.advanced_card)
        self.delete_preset_btn.setObjectName("secondaryButton")
        self.delete_preset_btn.clicked.connect(self._delete_preset)
        self.restore_defaults_btn = QPushButton("Restore Default Presets", self.advanced_card)
        self.restore_defaults_btn.setObjectName("secondaryButton")
        self.restore_defaults_btn.clicked.connect(self._restore_default_presets)
        for b in (self.save_preset_btn, self.rename_preset_btn, self.delete_preset_btn, self.restore_defaults_btn):
            preset_row.addWidget(b)
        preset_row.addStretch(1)
        a.addLayout(preset_row)

        limits = QLabel(
            "Supported now: 10-band graphic EQ, preamp, presets, enable/disable, reset, persistence. "
            "Not implemented as fake controls: parametric per-band Q/frequency editing, bass/treble enhancement effects, "
            "and additional DSP effects not provided by the current ISAI EQ pipeline.",
            self.advanced_card,
        )
        limits.setObjectName("pageSubtitle")
        limits.setWordWrap(True)
        a.addWidget(limits)
        self.body.addWidget(self.advanced_card)
        self.body.addStretch(1)

    def _title(self, text: str) -> QLabel:
        l = QLabel(text, self)
        l.setObjectName("sectionTitle")
        return l

    def _hint(self, text: str) -> QLabel:
        l = QLabel(text, self)
        l.setObjectName("pageSubtitle")
        l.setWordWrap(True)
        return l

    def _build_bands_row(self, parent: QWidget, prefix: str) -> QWidget:
        wrap = QWidget(parent)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._band_sliders = getattr(self, "_band_sliders", [])
        self._band_labels = getattr(self, "_band_labels", [])
        # We build two sets; store as (normal, advanced) by index using attributes
        sliders = []
        labels = []
        for i, freq in enumerate(BAND_LABELS):
            col = QVBoxLayout()
            col.setSpacing(4)
            val = QLabel("0 dB", wrap)
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setObjectName("pageSubtitle")
            s = QSlider(Qt.Orientation.Vertical, wrap)
            s.setRange(int(MIN_GAIN_DB), int(MAX_GAIN_DB))
            s.setValue(0)
            s.setTickInterval(6)
            s.setTickPosition(QSlider.TickPosition.TicksBothSides)
            s.setMinimumHeight(180)
            s.valueChanged.connect(lambda v, idx=i, lab=val: self._on_band_changed(idx, v, lab))
            name = QLabel(freq, wrap)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setObjectName("pageSubtitle")
            col.addWidget(val)
            col.addWidget(s, 0, Qt.AlignmentFlag.AlignHCenter)
            col.addWidget(name)
            row.addLayout(col, 1)
            sliders.append(s)
            labels.append(val)
        setattr(self, f"_{prefix}_sliders", sliders)
        setattr(self, f"_{prefix}_labels", labels)
        return wrap

    def _build_preamp_row(self, parent: QWidget, prefix: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Preamp", parent))
        slider = QSlider(Qt.Orientation.Horizontal, parent)
        slider.setRange(int(MIN_PREAMP_DB), int(MAX_PREAMP_DB))
        slider.setValue(0)
        slider.valueChanged.connect(lambda v: self._on_preamp_changed(v))
        val = QLabel("0 dB", parent)
        val.setObjectName("pageSubtitle")
        row.addWidget(slider, 1)
        row.addWidget(val)
        setattr(self, f"_{prefix}_preamp_slider", slider)
        setattr(self, f"_{prefix}_preamp_label", val)
        return row

    # ----------------------------------------------------------------- events

    def _on_mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        self._eq.set_mode(str(mode))

    def _on_preset_selected(self, name: str) -> None:
        if self._updating or not name:
            return
        self._eq.apply_preset(name)

    def _on_band_changed(self, index: int, value: int, label: QLabel) -> None:
        label.setText(f"{value:+d} dB")
        if self._updating:
            return
        self._eq.set_band(index, float(value))
        self._sync_sliders_from_state()  # keep both modes in sync

    def _on_preamp_changed(self, value: int) -> None:
        if self._updating:
            return
        self._eq.set_preamp(float(value))
        self._sync_sliders_from_state()

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name in BUILTIN_PRESETS:
            QMessageBox.warning(self, "Preset", "Built-in presets cannot be overwritten.")
            return
        if not self._eq.save_custom_preset(name):
            QMessageBox.warning(self, "Preset", "Could not save preset.")
        self._sync_from_state()

    def _rename_preset(self) -> None:
        current = self._eq.state.active_preset
        if self._eq.is_builtin_preset(current):
            QMessageBox.information(self, "Preset", "Built-in presets cannot be renamed.")
            return
        name, ok = QInputDialog.getText(self, "Rename Preset", "New name:", text=current)
        if not ok or not name.strip():
            return
        if not self._eq.rename_custom_preset(current, name.strip()):
            QMessageBox.warning(self, "Preset", "Could not rename preset.")
        self._sync_from_state()

    def _delete_preset(self) -> None:
        current = self._eq.state.active_preset
        if self._eq.is_builtin_preset(current):
            QMessageBox.information(self, "Preset", "Built-in presets cannot be deleted.")
            return
        confirm = QMessageBox.question(self, "Delete Preset", f"Delete custom preset '{current}'?")
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._eq.delete_custom_preset(current)
        self._sync_from_state()

    def _restore_default_presets(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Restore Default Presets",
            "Remove all custom presets and reset equalizer to Flat? Built-in presets will remain available.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._eq.state.custom_presets.clear()
        self._eq.apply_preset("Flat")
        self._sync_from_state()

    # ------------------------------------------------------------------- sync

    def _sync_from_state(self) -> None:
        self._updating = True
        try:
            st = self._eq.state
            self.enable_btn.setChecked(bool(st.enabled))
            self.enable_btn.setText("Enabled" if st.enabled else "Disabled")
            # mode
            idx = self.mode_combo.findData(st.mode)
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
            self.normal_card.setVisible(st.mode == "normal")
            self.advanced_card.setVisible(st.mode == "advanced")
            # presets
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            for name in self._eq.presets():
                self.preset_combo.addItem(name)
            if st.active_preset not in self._eq.presets():
                self.preset_combo.addItem(st.active_preset)
            i = self.preset_combo.findText(st.active_preset)
            if i >= 0:
                self.preset_combo.setCurrentIndex(i)
            self.preset_combo.blockSignals(False)
            self._sync_sliders_from_state()
        finally:
            self._updating = False

    def _sync_sliders_from_state(self) -> None:
        st = self._eq.state
        for prefix in ("n", "a"):
            sliders = getattr(self, f"_{prefix}_sliders", [])
            labels = getattr(self, f"_{prefix}_labels", [])
            for i, sl in enumerate(sliders):
                sl.blockSignals(True)
                sl.setValue(int(round(st.bands[i])))
                sl.blockSignals(False)
                if i < len(labels):
                    labels[i].setText(f"{int(round(st.bands[i])):+d} dB")
            ps = getattr(self, f"_{prefix}_preamp_slider", None)
            pl = getattr(self, f"_{prefix}_preamp_label", None)
            if ps is not None:
                ps.blockSignals(True)
                ps.setValue(int(round(st.preamp_db)))
                ps.blockSignals(False)
            if pl is not None:
                pl.setText(f"{int(round(st.preamp_db)):+d} dB")
        self.response.set_values(st.bands, st.preamp_db, self._colors)

    # ------------------------------------------------------------------ theme

    def refresh_theme(self, colors: ThemeColors) -> None:
        self._colors = colors
        self.response.set_values(self._eq.state.bands, self._eq.state.preamp_db, colors)

    def refresh_library(self) -> None:
        self._sync_from_state()
