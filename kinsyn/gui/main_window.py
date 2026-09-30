"""Main window: library | mechanism view | editor + analysis, with playback
and circuit plots along the bottom."""

import html
import math
import re

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from kinsyn.core.analysis import analyze, circuit_derivatives, mechanical_advantage, trace_circuit
from kinsyn.core.families import FourBar
from kinsyn.core.mechanism import REGISTRY
from kinsyn.core.units import LENGTH_UNITS, format_angle, format_length
from kinsyn.library.catalog import Entry, save_user_entry

from .editor import ParamEditor, ValueField
from .library_panel import LibraryPanel
from .plots import CircuitPlots
from .settings import DEFAULTS, PreferencesDialog, Settings, apply_app_font, clamp_font
from .view import MechanismView

SPEEDS = [("0.25x", 0.25), ("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0), ("4x", 4.0)]
N_SAMPLES = 720
CYCLE_SECONDS = 4.0  # one circuit at 1x speed


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("kinsyn: planar kinematic synthesis")
        self.resize(1500, 950)
        self.settings = Settings()
        self.prefs = {k: self.settings.get(k) for k in DEFAULTS}
        apply_app_font(self.prefs["ui/font_pt"])
        self.unit = self.prefs["units/default"]
        self.mech = FourBar()
        self.operating = None  # (lo, hi) in input units, or None
        self.circuit_index = 0
        self.circuit = None
        self.index = 0.0
        self.speed_rpm = 60.0  # rotary input speed
        self.speed_lin = 50.0  # linear input speed, mm/s
        self.source = None  # library entry the current design started from
        self.baseline = (self.mech, None)  # what Reset restores
        self.mu_limit = math.radians(self.prefs["analysis/mu_limit_deg"])

        self.view = MechanismView()
        self.setCentralWidget(self.view)

        # Library (left)
        self.library = LibraryPanel()
        self.library.entrySelected.connect(self.load_entry)
        self.setCorner(QtCore.Qt.BottomLeftCorner, QtCore.Qt.LeftDockWidgetArea)
        self.setCorner(QtCore.Qt.BottomRightCorner, QtCore.Qt.RightDockWidgetArea)
        lib_dock = self._dock("Library", self.library, QtCore.Qt.LeftDockWidgetArea)

        # Editor + analysis (right)
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        self.editor = ParamEditor()
        self.editor.changed.connect(self.on_edit)
        self.editor.typeChanged.connect(self.on_type)
        head = QtWidgets.QHBoxLayout()
        self.source_label = QtWidgets.QLabel()
        self.source_label.setTextFormat(QtCore.Qt.RichText)
        head.addWidget(self.source_label, 1)
        self.reset_btn = QtWidgets.QPushButton("Reset")
        self.reset_btn.setToolTip("Restore the template's original dimensions and operating range (Ctrl+R)")
        self.reset_btn.clicked.connect(self.reset_mechanism)
        head.addWidget(self.reset_btn)
        rl.addLayout(head)
        rl.addWidget(self.editor)
        rl.addWidget(self._build_motion_box())
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(QtCore.Qt.RichText)
        self.summary.setAlignment(QtCore.Qt.AlignTop)
        rl.addWidget(self.summary, 1)
        save = QtWidgets.QPushButton("Save to library…")
        save.clicked.connect(self.save_to_library)
        rl.addWidget(save)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(right)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(440)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        mech_dock = self._dock("Mechanism", scroll, QtCore.Qt.RightDockWidgetArea)

        # Playback + plots (bottom)
        bottom = QtWidgets.QWidget()
        bl = QtWidgets.QVBoxLayout(bottom)
        bl.addLayout(self._build_playback())
        self.plots = CircuitPlots(self.settings.get_raw("plots/panels"))
        self.plots.scrubbed.connect(self.seek)
        self.plots.panelsChanged.connect(lambda keys: self.settings.set_raw("plots/panels", keys))
        bl.addWidget(self.plots)
        motion_dock = self._dock("Motion", bottom, QtCore.Qt.BottomDockWidgetArea)
        self.resizeDocks([lib_dock, mech_dock], [280, 460], QtCore.Qt.Horizontal)
        self.resizeDocks([motion_dock], [270], QtCore.Qt.Vertical)

        # Status bar: units
        self.unit_combo = QtWidgets.QComboBox()
        self.unit_combo.addItems(list(LENGTH_UNITS))
        self.unit_combo.setCurrentText(self.unit)
        self.unit_combo.currentTextChanged.connect(self.set_units)
        self.statusBar().addPermanentWidget(QtWidgets.QLabel("Units:"))
        self.statusBar().addPermanentWidget(self.unit_combo)

        self._build_menu()
        self._default_layout = self.saveState()
        self.editor.set_units(self.unit)
        self.view.set_units(self.unit)
        self._apply_fonts()
        geo, state = self.settings.get_raw("window/geometry"), self.settings.get_raw("window/state")
        if geo is not None:
            self.restoreGeometry(geo)
        if state is not None:
            self.restoreState(state)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.editor.set_mechanism(self.mech)
        self.recompute(autorange=True)
        self.timer.start()

    # --- construction ----------------------------------------------------
    def _dock(self, title, widget, area):
        dock = QtWidgets.QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFloatable)
        self.addDockWidget(area, dock)
        return dock

    def _build_menu(self):
        m = self.menuBar().addMenu("&File")
        act = QtGui.QAction("Save to library…", self, shortcut="Ctrl+S", triggered=self.save_to_library)
        m.addAction(act)
        m.addAction(QtGui.QAction("Quit", self, shortcut="Ctrl+Q", triggered=self.close))
        e = self.menuBar().addMenu("&Edit")
        e.addAction(QtGui.QAction("Reset mechanism", self, shortcut="Ctrl+R", triggered=self.reset_mechanism))
        e.addAction(QtGui.QAction("Preferences…", self, shortcut="Ctrl+,", triggered=self.show_preferences))
        v = self.menuBar().addMenu("&View")
        v.addAction(QtGui.QAction("Larger text", self, shortcuts=["Ctrl+=", "Ctrl++"],
                                  triggered=lambda: self.change_text_size(+0.5)))
        v.addAction(QtGui.QAction("Smaller text", self, shortcut="Ctrl+-",
                                  triggered=lambda: self.change_text_size(-0.5)))
        v.addAction(QtGui.QAction("Default text size", self, shortcut="Ctrl+0",
                                  triggered=lambda: self.change_text_size(None)))
        v.addSeparator()
        v.addAction(QtGui.QAction("Fit to window", self, shortcut="F", triggered=self.view.autorange))
        v.addAction(QtGui.QAction("Play / pause", self, shortcut="Space", triggered=self.toggle_play))

    def _build_motion_box(self):
        box = QtWidgets.QGroupBox("Motion")
        form = QtWidgets.QFormLayout(box)
        self.circuit_combo = QtWidgets.QComboBox()
        self.circuit_combo.activated.connect(self.on_circuit)
        form.addRow("Circuit", self.circuit_combo)
        self.limit_check = QtWidgets.QCheckBox("Limit input to an operating range")
        self.limit_check.toggled.connect(self.on_limit_toggled)
        form.addRow(self.limit_check)
        row = QtWidgets.QWidget()
        hl = QtWidgets.QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        self.op_lo = ValueField("angle", self.unit)
        self.op_hi = ValueField("angle", self.unit)
        self.op_lo.committed.connect(self.on_operating_edit)
        self.op_hi.committed.connect(self.on_operating_edit)
        hl.addWidget(QtWidgets.QLabel("from"))
        hl.addWidget(self.op_lo)
        hl.addWidget(QtWidgets.QLabel("to"))
        hl.addWidget(self.op_hi)
        self.op_row = row
        form.addRow(row)
        # Constant input speed used for the velocity / acceleration plots.
        srow = QtWidgets.QWidget()
        sl = QtWidgets.QHBoxLayout(srow)
        sl.setContentsMargins(0, 0, 0, 0)
        self.speed_field = QtWidgets.QDoubleSpinBox()
        self.speed_field.setRange(0.001, 1e6)
        self.speed_field.setDecimals(3)
        self.speed_field.setKeyboardTracking(False)
        self.speed_field.valueChanged.connect(self.on_speed_edit)
        sl.addWidget(self.speed_field, 1)
        form.addRow("Input speed", srow)
        return box

    def _build_playback(self):
        hl = QtWidgets.QHBoxLayout()
        self.play_btn = QtWidgets.QPushButton("Pause")
        self.play_btn.setFixedWidth(80)
        self.play_btn.clicked.connect(self.toggle_play)
        hl.addWidget(self.play_btn)
        self.speed = QtWidgets.QComboBox()
        for label, v in SPEEDS:
            self.speed.addItem(label, v)
        self.speed.setCurrentIndex(2)
        hl.addWidget(self.speed)
        self.scrub = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.scrub.setRange(0, N_SAMPLES - 1)
        self.scrub.valueChanged.connect(lambda i: self.seek(i) if self.scrub.isSliderDown() else None)
        self.scrub.sliderPressed.connect(lambda: self.set_playing(False))
        hl.addWidget(self.scrub, 1)
        # Fixed-width font + padded fields so the readout never changes width
        # (a changing width would shove the scrub slider around).
        self.readout = QtWidgets.QLabel()
        self.readout.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        self.readout.setTextFormat(QtCore.Qt.PlainText)
        hl.addWidget(self.readout)
        return hl

    # --- model updates ---------------------------------------------------
    def load_entry(self, entry):
        self.source = entry
        self.baseline = (entry.mechanism, entry.operating_range)
        self.mech = entry.mechanism
        self.operating = entry.operating_range
        self.circuit_index = 0
        self.editor.set_mechanism(self.mech)
        self.index = 0.0
        self.recompute(autorange=True)

    def on_type(self, kind):
        if kind != self.mech.kind:
            self.mech = REGISTRY[kind]()
            self.operating = None
            self.source = None
            self.baseline = (self.mech, None)
            self.circuit_index = 0
            self.editor.set_mechanism(self.mech)
            self.recompute(autorange=True)

    def on_edit(self, mech):
        driver_changed = getattr(mech, "driver", None) != getattr(self.mech, "driver", None)
        self.mech = mech
        if driver_changed:
            self.operating = None
            self.circuit_index = 0
        self.recompute(autorange=driver_changed)

    def on_circuit(self, i):
        self.circuit_index = i
        self.recompute()

    def on_limit_toggled(self, on):
        if on and self.operating is None:
            # Default to the current circuit's input range, trimmed a little.
            lo, hi = self.circuit.interval if self.circuit else (0.0, 1.0)
            if self.circuit and self.circuit.full_rotation:
                lo, hi = lo, lo + math.pi / 2
            self.operating = (lo, hi)
        elif not on:
            self.operating = None
        self.recompute()

    def on_operating_edit(self, _):
        self.operating = (self.op_lo.value, self.op_hi.value)
        self.recompute()

    def _input_speed(self):
        """Input speed in rad/s (rotary) or mm/s (linear)."""
        if self.mech.input_kind == "angle":
            return self.speed_rpm * 2 * math.pi / 60
        return self.speed_lin

    def _update_speed_field(self):
        self.speed_field.blockSignals(True)
        if self.mech.input_kind == "angle":
            self.speed_field.setSuffix(" rpm")
            self.speed_field.setValue(self.speed_rpm)
        else:
            self.speed_field.setSuffix(f" {self.unit}/s")
            self.speed_field.setValue(self.speed_lin / LENGTH_UNITS[self.unit])
        self.speed_field.blockSignals(False)

    def on_speed_edit(self, v):
        if self.mech.input_kind == "angle":
            self.speed_rpm = v
        else:
            self.speed_lin = v * LENGTH_UNITS[self.unit]
        self.recompute()

    def reset_mechanism(self):
        """Restore the template (or type defaults) the design started from."""
        self.mech, self.operating = self.baseline
        self.circuit_index = 0
        self.editor.set_mechanism(self.mech)  # rebuild: resets slider ranges too
        self.recompute(autorange=True)
        self.statusBar().showMessage("Reset to " + (self.source.name if self.source else "defaults"), 2000)

    def _update_source_label(self):
        modified = (self.mech, self.operating) != self.baseline
        name = html.escape(self.source.name) if self.source else f"New {html.escape(self.mech.title)}"
        tag = " <span style='color:#f0a04b'>(modified)</span>" if modified else ""
        self.source_label.setText(f"<b>{name}</b>{tag}")
        self.reset_btn.setEnabled(modified)

    def recompute(self, autorange=False):
        self._update_source_label()
        self._update_speed_field()
        intervals, full, circuit, summary = analyze(self.mech, self.circuit_index, N_SAMPLES,
                                                    self.operating, self.mu_limit)
        self.circuit = circuit
        self._update_motion_box(intervals, full)
        if circuit is None:
            self.view.clear_mechanism()
            reason = ("The operating range is outside the range where the mechanism assembles."
                      if self.operating and intervals else "These dimensions cannot be assembled.")
            self.summary.setText(f"<p style='color:#ef5350'><b>{reason}</b></p>")
            self.readout.setText("")
            return
        others = []
        if self.operating is None:
            if full and self.mech.has_branches:
                others.append(trace_circuit(self.mech.copy(branch=-self.mech.branch), intervals[0], True,
                                            N_SAMPLES).frames)
            for j, iv in enumerate(intervals):
                if j != self.circuit_index and not full:
                    others.append(trace_circuit(self.mech, iv, False, N_SAMPLES).frames)
        toggles = [i for i, _ in summary.toggles]
        self.view.set_circuit(self.mech, circuit, others, toggles, autorange)
        ma = mechanical_advantage(self.mech, circuit)
        derivs = circuit_derivatives(self.mech, circuit, self._input_speed())
        self.plots.set_data(self.mech, circuit, derivs, ma, self.unit, self.mu_limit)
        self.summary.setText(self._summary_html(summary, intervals, full))
        self._ma = ma
        self.scrub.setRange(0, len(circuit.q) - 1)
        self.index = min(self.index, len(circuit.q) - 1)
        self.show_index(int(self.index))

    def _update_motion_box(self, intervals, full):
        self.circuit_combo.blockSignals(True)
        self.circuit_combo.clear()
        if full:
            self.circuit_combo.addItem("Full rotation")
        else:
            for lo, hi in intervals:
                self.circuit_combo.addItem(f"Input {self._fmt_in(lo)} to {self._fmt_in(hi)}")
        self.circuit_combo.setCurrentIndex(min(self.circuit_index, self.circuit_combo.count() - 1))
        self.circuit_combo.setEnabled(self.operating is None and self.circuit_combo.count() > 1)
        self.circuit_combo.blockSignals(False)

        kind = "angle" if self.mech.input_kind == "angle" else "length"
        for f in (self.op_lo, self.op_hi):
            f.kind = kind
            f.set_unit(self.unit)
        self.limit_check.blockSignals(True)
        self.limit_check.setChecked(self.operating is not None)
        self.limit_check.blockSignals(False)
        self.op_row.setEnabled(self.operating is not None)
        if self.operating is not None:
            self.op_lo.set_value(self.operating[0])
            self.op_hi.set_value(self.operating[1])
        else:
            self.op_lo.clear()
            self.op_hi.clear()

    # --- formatting ------------------------------------------------------
    def _fmt_in(self, v):
        if self.mech.input_kind == "angle":
            return f"{format_angle(v, 1)}°"
        return f"{format_length(v, self.unit)} {self.unit}"

    def _fmt_out(self, v):
        if self.mech.output_kind == "angle":
            return f"{format_angle(v, 1)}°"
        return f"{format_length(v, self.unit)} {self.unit}"

    def _summary_html(self, s, intervals, full):
        rows = [("Class", f"<b>{html.escape(s.classification)}</b>")]
        if full:
            rows.append(("Input", "rotates fully"))
        else:
            rows.append(("Input", "rocks: " + ", ".join(f"{self._fmt_in(a)} to {self._fmt_in(b)}"
                                                         for a, b in intervals)))
        if s.output_rotates:
            rows.append(("Output", "rotates fully"))
        else:
            lo, hi = s.output_range
            span = f"{format_angle(hi - lo, 1)}°" if self.mech.output_kind == "angle" else \
                f"{format_length(hi - lo, self.unit)} {self.unit}"
            rows.append(("Output travel", f"{span}  ({self._fmt_out(lo)} to {self._fmt_out(hi)})"))
        if math.isfinite(s.mu_min):
            bad = s.mu_min < self.mu_limit
            color = "#ef5350" if bad else "#66bb6a"
            rows.append(("Transmission angle",
                         f"{format_angle(s.mu_range[0], 1)}° to {format_angle(s.mu_range[1], 1)}°, "
                         f"worst <span style='color:{color}'>{format_angle(s.mu_min, 1)}°</span>"))
        if s.time_ratio:
            rows.append(("Time ratio", f"{s.time_ratio:.3f}"))
        if s.toggles:
            wrap = (lambda q: q % (2 * math.pi)) if self.mech.input_kind == "angle" else (lambda q: q)
            rows.append(("Toggle positions", ", ".join(self._fmt_in(wrap(q)) for _, q in s.toggles)))
        if s.over_center is not None:
            val = (f"{format_angle(s.over_center, 2)}°" if self.mech.input_kind == "angle"
                   else f"{format_length(s.over_center, self.unit)} {self.unit}")
            rows.append(("Over-center", f"<span style='color:#66bb6a'>{val} past toggle</span>"))
        table = "".join(f"<tr><td style='color:#8a93a3;padding-right:10px'>{k}</td><td>{v}</td></tr>"
                        for k, v in rows)
        notes = "".join(f"<li>{html.escape(n)}</li>" for n in s.notes)
        warns = "".join(f"<li style='color:#ef5350'>{html.escape(w)}</li>" for w in s.warnings)
        return f"<table>{table}</table><ul>{warns}{notes}</ul>"

    # --- playback --------------------------------------------------------
    def set_playing(self, on):
        if on:
            self.timer.start()
        else:
            self.timer.stop()
        self.play_btn.setText("Pause" if on else "Play")

    def toggle_play(self):
        self.set_playing(not self.timer.isActive())

    def _tick(self):
        if self.circuit is None:
            return
        n = len(self.circuit.q)
        # One input sweep of the base interval takes CYCLE_SECONDS at 1x.
        step = N_SAMPLES * self.timer.interval() / 1000.0 / CYCLE_SECONDS * self.speed.currentData()
        self.index = (self.index + step) % n
        self.show_index(int(self.index))

    def seek(self, i):
        self.set_playing(False)
        self.index = float(i)
        self.show_index(i)

    def show_index(self, i):
        if self.circuit is None:
            return
        self.view.show_frame(i)
        self.plots.set_index(i)
        self.scrub.blockSignals(True)
        self.scrub.setValue(i)
        self.scrub.blockSignals(False)
        f = self.circuit.frames
        self.readout.setText(self._readout_text(f.q[i], f.output[i], f.mu[i], self._ma[i],
                                                self.mech.input_kind, self.mech.output_kind, self.unit))

    @staticmethod
    def _readout_text(q, out, mu, ma, in_kind, out_kind, unit):
        def val(v, kind):
            if kind == "angle":
                return f"{math.degrees(v) % 360:9.1f}°   "
            return f"{v / LENGTH_UNITS[unit]:10.3f} {unit:<2}"

        mu_txt = f"{math.degrees(mu):5.1f}°" if np.isfinite(mu) else "  n/a "
        ma_txt = f"{ma:8.2f}" if np.isfinite(ma) and ma < 1e4 else "       ∞"
        return f"input {val(q, in_kind)}  output {val(out, out_kind)}  μ {mu_txt}  MA {ma_txt}"

    # --- preferences ---------------------------------------------------
    def _apply_fonts(self):
        apply_app_font(self.prefs["ui/font_pt"])
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        f.setPointSizeF(self.prefs["ui/font_pt"])
        self.readout.setFont(f)
        self.readout.setFixedWidth(QtGui.QFontMetrics(f).horizontalAdvance(
            self._readout_text(-99999.999, -99999.999, 179.9, 99999.99, "length", "length", "mm") + "  "))
        self.plots.set_font(self.prefs["ui/plot_font_pt"])
        self.view.set_font(self.prefs["ui/plot_font_pt"])

    def apply_preferences(self, values):
        self.prefs.update(values)
        for k, v in values.items():
            self.settings.set(k, v)
        self._apply_fonts()
        mu_limit = math.radians(self.prefs["analysis/mu_limit_deg"])
        if mu_limit != self.mu_limit:
            self.mu_limit = mu_limit
            self.recompute()

    def change_text_size(self, delta):
        if delta is None:
            ui, plot = DEFAULTS["ui/font_pt"], DEFAULTS["ui/plot_font_pt"]
        else:
            ui = clamp_font(self.prefs["ui/font_pt"] + delta)
            plot = clamp_font(self.prefs["ui/plot_font_pt"] + delta)
        self.apply_preferences({"ui/font_pt": ui, "ui/plot_font_pt": plot})
        self.statusBar().showMessage(f"Text size {ui:g} pt (plots {plot:g} pt)", 2000)

    def show_preferences(self):
        dlg = PreferencesDialog(self.prefs, self)
        dlg.applied.connect(self.apply_preferences)
        dlg.resetLayout.connect(lambda: self.restoreState(self._default_layout))
        dlg.exec()

    def closeEvent(self, event):
        self.settings.set_raw("window/geometry", self.saveGeometry())
        self.settings.set_raw("window/state", self.saveState())
        super().closeEvent(event)

    # --- units / library -------------------------------------------------
    def set_units(self, unit):
        self.unit = unit
        self.editor.set_units(unit)
        self.view.set_units(unit)
        self.recompute()

    def save_to_library(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Save to library", "Name:")
        if not ok or not name.strip():
            return
        notes, _ = QtWidgets.QInputDialog.getMultiLineText(self, "Save to library", "Notes (optional):")
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "design"
        entry = Entry(id=f"user_{slug}", name=name.strip(), group="My designs",
                      description=notes, mechanism=self.mech, tags=["mine"],
                      operating_range=self.operating, builtin=False)
        path = save_user_entry(entry)
        self.library.reload()
        self.statusBar().showMessage(f"Saved to {path}", 5000)
