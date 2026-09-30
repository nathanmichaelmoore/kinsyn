"""Plots along the circuit (transmission angle, output, mechanical advantage)
with a draggable cursor that scrubs the animation."""

import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from kinsyn.core.units import LENGTH_UNITS

CURSOR = "#f0a04b"
BAD = (239, 83, 80, 40)


class CircuitPlots(QtWidgets.QWidget):
    scrubbed = QtCore.Signal(int)

    def __init__(self):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.n = 1
        self.plots, self.curves, self.cursors = [], [], []
        titles = ("Transmission angle (deg)", "Output", "Mechanical advantage")
        for title in titles:
            w = pg.PlotWidget(title=title)
            w.showGrid(x=True, y=True, alpha=0.12)
            w.setLabel("bottom", "circuit position (%)")
            w.getPlotItem().hideButtons()
            w.setMouseEnabled(x=False, y=False)
            curve = w.plot(pen=pg.mkPen("#4fc3f7", width=2))
            cursor = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(CURSOR, width=2))
            cursor.sigPositionChanged.connect(self._on_cursor)
            w.addItem(cursor)
            lay.addWidget(w)
            self.plots.append(w)
            self.curves.append(curve)
            self.cursors.append(cursor)
        self.mu_plot, self.out_plot, self.ma_plot = self.plots
        self.ma_plot.setLogMode(y=True)
        self.mu_limit = None
        self._busy = False

    def set_data(self, mech, circuit, ma, unit, mu_limit):
        f = circuit.frames
        self.n = len(f.q)
        x = np.arange(self.n) * 100.0 / self.n
        mu = np.degrees(f.mu)
        if np.isfinite(mu).any():
            self.curves[0].setData(x, mu, connect="finite")
        else:
            self.curves[0].setData([], [])
        self.mu_plot.setYRange(0, 180)
        if self.mu_limit is None:
            lim = math.degrees(mu_limit)
            self.mu_bands = [pg.LinearRegionItem((0, lim), orientation="horizontal", movable=False, brush=BAD),
                             pg.LinearRegionItem((180 - lim, 180), orientation="horizontal", movable=False, brush=BAD)]
            for b in self.mu_bands:
                b.setZValue(-10)
                for line in b.lines:
                    line.setPen(pg.mkPen(None))
                self.mu_plot.addItem(b)
            self.mu_limit = lim

        out = f.output
        if mech.output_kind == "angle":
            out = np.degrees(np.unwrap(out))
            label = f"{mech.output_label} (deg)"
        else:
            out = out / LENGTH_UNITS[unit]
            label = f"{mech.output_label} ({unit})"
        self.out_plot.setTitle(label)
        self.curves[1].setData(x, out)

        m = np.where(np.isfinite(ma) & (ma > 0), ma, np.nan)
        m = np.clip(m, 1e-3, 1e3)
        self.curves[2].setData(x, m, connect="finite")
        unit_note = "" if mech.input_kind == mech.output_kind else (
            " (per mm)" if mech.output_kind == "length" else " (mm)")
        self.ma_plot.setTitle("Mechanical advantage" + unit_note)

    def set_index(self, i):
        self._busy = True
        for c in self.cursors:
            c.setValue(i * 100.0 / self.n)
        self._busy = False

    def _on_cursor(self, line):
        if self._busy:
            return
        i = int(round(line.value() / 100.0 * self.n)) % self.n
        self.set_index(i)
        self.scrubbed.emit(i)
