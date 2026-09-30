"""Plots along the circuit. Each panel has a selector for what it shows
(transmission angle, output position / velocity / acceleration, coupler
point speed / acceleration, mechanical advantage). A draggable cursor on any
panel scrubs the animation."""

import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from kinsyn.core.units import LENGTH_UNITS

from kinsyn.help.topics import PLOT_TERMS, TERMS

from .style import style_plot

CURSOR = "#f0a04b"
BAD = (239, 83, 80, 40)

QUANTITIES = [
    ("mu", "Transmission angle"),
    ("out", "Output position"),
    ("out_vel", "Output velocity"),
    ("out_acc", "Output acceleration"),
    ("p_speed", "Coupler point speed"),
    ("p_acc", "Coupler point acceleration"),
    ("ma", "Mechanical advantage"),
]
DEFAULT_PANELS = ["mu", "out", "out_vel", "out_acc"]


class PlotPanel(QtWidgets.QWidget):
    helpRequested = QtCore.Signal(str)

    def __init__(self, key):
        super().__init__()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.combo = QtWidgets.QComboBox()
        for k, label in QUANTITIES:
            self.combo.addItem(label, k)
            self.combo.setItemData(self.combo.count() - 1, TERMS[PLOT_TERMS[k]][1], QtCore.Qt.ToolTipRole)
        self.combo.setCurrentIndex(self.combo.findData(key))
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(2)
        head.addWidget(self.combo, 1)
        q = QtWidgets.QToolButton()
        q.setText("?")
        q.setAutoRaise(True)
        q.setToolTip("What does this plot mean?")
        q.clicked.connect(lambda: self.helpRequested.emit(PLOT_TERMS[self.key]))
        head.addWidget(q)
        lay.addLayout(head)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.12)
        self.plot.getPlotItem().hideButtons()
        self.plot.setMouseEnabled(x=False, y=False)
        lay.addWidget(self.plot, 1)
        self.curve = self.plot.plot(pen=pg.mkPen("#4fc3f7", width=2))
        self.cursor = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(CURSOR, width=2))
        self.plot.addItem(self.cursor)
        self.bands = [pg.LinearRegionItem((0, 0), orientation="horizontal", movable=False, brush=BAD)
                      for _ in range(2)]
        for b in self.bands:
            b.setZValue(-10)
            for line in b.lines:
                line.setPen(pg.mkPen(None))
            self.plot.addItem(b)

    @property
    def key(self):
        return self.combo.currentData()


class CircuitPlots(QtWidgets.QWidget):
    scrubbed = QtCore.Signal(int)
    panelsChanged = QtCore.Signal(list)
    helpRequested = QtCore.Signal(str)

    def __init__(self, keys=None):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.n = 1
        self.pt = 9.0
        self._data = None
        self._busy = False
        self.panels = []
        valid = dict(QUANTITIES)
        for key in (keys or DEFAULT_PANELS):
            p = PlotPanel(key if key in valid else "mu")
            p.cursor.sigPositionChanged.connect(self._on_cursor)
            p.combo.currentIndexChanged.connect(self._on_panel_changed)
            p.helpRequested.connect(self.helpRequested)
            lay.addWidget(p)
            self.panels.append(p)
        self.set_font(self.pt)

    def keys(self):
        return [p.key for p in self.panels]

    def set_font(self, pt):
        self.pt = pt
        for p in self.panels:
            style_plot(p.plot.getPlotItem(), pt, labels={"bottom": "circuit position (%)"})
        self._redraw()

    def _on_panel_changed(self, _):
        self.panelsChanged.emit(self.keys())
        self._redraw()

    def set_data(self, mech, circuit, derivs, ma, unit, mu_limit):
        self._data = (mech, circuit, derivs, ma, unit, mu_limit)
        self.n = len(circuit.q)
        self._redraw()

    def _series(self, key):
        """(y values, axis label, log scale) for a quantity."""
        mech, circuit, d, ma, unit, _ = self._data
        f = circuit.frames
        L = LENGTH_UNITS[unit]
        ang = mech.output_kind == "angle"
        if key == "mu":
            return np.degrees(f.mu), "deg", False
        if key == "out":
            return (np.degrees(np.unwrap(f.output)), "deg", False) if ang else (f.output / L, unit, False)
        if key == "out_vel":
            return (np.degrees(d["output_vel"]), "deg/s", False) if ang else (d["output_vel"] / L, f"{unit}/s", False)
        if key == "out_acc":
            return (np.degrees(d["output_acc"]), "deg/s²", False) if ang else (d["output_acc"] / L, f"{unit}/s²", False)
        if key == "p_speed":
            return np.abs(d["P_vel"]) / L, f"{unit}/s", False
        if key == "p_acc":
            return np.abs(d["P_acc"]) / L, f"{unit}/s²", False
        m = np.where(np.isfinite(ma) & (ma > 0), ma, np.nan)
        note = "" if mech.input_kind == mech.output_kind else (" per mm" if mech.output_kind == "length" else " mm")
        return np.clip(m, 1e-3, 1e3), "ratio" + note, True

    def _redraw(self):
        if not self._data:
            return
        mech, circuit, _, _, _, mu_limit = self._data
        x = np.arange(self.n) * 100.0 / self.n
        for p in self.panels:
            y, ylabel, log = self._series(p.key)
            title = dict(QUANTITIES)[p.key]
            base = mech.output_label.replace(" position", "").replace(" angle", "")
            title = {"out": mech.output_label, "out_vel": f"{base} velocity",
                     "out_acc": f"{base} acceleration"}.get(p.key, title)
            if p.plot.getPlotItem().ctrl.logYCheck.isChecked() != log:
                # Reset the range first: an old linear range read as log10 overflows.
                p.plot.setYRange(0, 1, padding=0)
                p.plot.setLogMode(y=log)
            if np.isfinite(y).any():
                p.curve.setData(x, y, connect="finite")
            else:
                p.curve.setData([], [])
            is_mu = p.key == "mu"
            lim = math.degrees(mu_limit)
            p.bands[0].setRegion((0, lim) if is_mu else (0, 0))
            p.bands[1].setRegion((180 - lim, 180) if is_mu else (0, 0))
            for b in p.bands:
                b.setVisible(is_mu)
            if is_mu:
                p.plot.setYRange(0, 180)
            else:
                p.plot.enableAutoRange(axis="y")
            style_plot(p.plot.getPlotItem(), self.pt, title=title,
                       labels={"left": ylabel, "bottom": "circuit position (%)"})

    def set_index(self, i):
        self._busy = True
        for p in self.panels:
            p.cursor.setValue(i * 100.0 / self.n)
        self._busy = False

    def _on_cursor(self, line):
        if self._busy:
            return
        i = int(round(line.value() / 100.0 * self.n)) % self.n
        self.set_index(i)
        self.scrubbed.emit(i)
