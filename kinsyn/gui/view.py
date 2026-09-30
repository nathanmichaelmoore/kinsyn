"""Canvas that draws and animates a mechanism along a traced circuit."""

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from kinsyn.core.units import LENGTH_UNITS

from .style import style_plot

LINK = "#c8d0dc"
COUPLER = "#f0a04b"
CURVE = "#4fc3f7"
CURVE_OTHER = "#4fc3f7"
GROUND = "#8a93a3"
PIN_FILL = "#1e2127"
TOGGLE = "#ef5350"


class MechanismView(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAspectLocked(True)
        self.showGrid(x=True, y=True, alpha=0.12)
        self.getPlotItem().hideButtons()
        self.factor = 1.0  # mm per display unit
        self.mech = None
        self.circuit = None
        self.drawing = None
        self._structure = None
        self._link_items = []
        self._block_items = []

        self.other_curves = []  # dim curves of the other circuits
        self.curve = pg.PlotDataItem(pen=pg.mkPen(CURVE, width=2))
        self.addItem(self.curve)
        self.toggle_marks = pg.ScatterPlotItem(symbol="x", size=12, pen=pg.mkPen(TOGGLE, width=2),
                                               brush=None)
        self.addItem(self.toggle_marks)
        self.rail_items = []
        self.ground_marks = pg.ScatterPlotItem(symbol="t1", size=22, pen=pg.mkPen(GROUND, width=2),
                                               brush=pg.mkBrush(GROUND + "40"))
        self.pins = pg.ScatterPlotItem(symbol="o", size=10, pen=pg.mkPen(LINK, width=2),
                                       brush=pg.mkBrush(PIN_FILL))
        self.tracer = pg.ScatterPlotItem(symbol="o", size=11, pen=pg.mkPen(CURVE, width=2),
                                         brush=pg.mkBrush(CURVE))
        for item in (self.ground_marks,):
            self.addItem(item)
        self._top_items = [self.pins, self.tracer]
        for item in self._top_items:
            item.setZValue(20)
            self.addItem(item)
        self.set_units("mm")

    # --- coordinates -----------------------------------------------------
    def _xy(self, z):
        z = np.asarray(z) / self.factor
        return z.real, z.imag

    def set_units(self, unit):
        self.factor = LENGTH_UNITS[unit]
        self.unit = unit
        style_plot(self.getPlotItem(), getattr(self, "pt", 9.0), labels={"bottom": unit, "left": unit})
        if self.circuit is not None:
            self._draw_static()
            self.autorange()

    def set_font(self, pt):
        self.pt = pt
        style_plot(self.getPlotItem(), pt, labels={"bottom": self.unit, "left": self.unit})

    # --- content ---------------------------------------------------------
    def clear_mechanism(self):
        self.mech = self.circuit = self.drawing = None
        self._rebuild([], [])
        self.curve.setData([], [])
        self.toggle_marks.setData([])
        self.ground_marks.setData([])
        self.pins.setData([])
        self.tracer.setData([])
        for it in self.other_curves + self.rail_items:
            self.removeItem(it)
        self.other_curves, self.rail_items = [], []

    def set_circuit(self, mech, circuit, others=(), toggles=(), autorange=False):
        """Show `circuit` of `mech`. `others` are frames of the remaining
        circuits (drawn dim); `toggles` are circuit indices of toggle points."""
        self.mech, self.circuit, self.drawing = mech, circuit, mech.drawing()
        self._others = list(others)
        self._toggles = list(toggles)
        structure = (tuple(self.drawing.links), tuple(b[0] for b in self.drawing.blocks))
        if structure != self._structure:
            self._rebuild(self.drawing.links, self.drawing.blocks)
            self._structure = structure
        self._draw_static()
        if autorange:
            self.autorange()

    def autorange(self):
        if self.circuit is None:
            return
        pts = [v for k, v in self.circuit.frames.points.items() if not k.startswith("dir:")]
        z = np.concatenate([np.ravel(p) for p in pts]) / self.factor
        z = z[np.isfinite(z)]
        if len(z):
            pad = 0.12 * max(np.ptp(z.real), np.ptp(z.imag), 1e-9)
            self.setRange(xRange=(z.real.min() - pad, z.real.max() + pad),
                          yRange=(z.imag.min() - pad, z.imag.max() + pad), padding=0)

    def _rebuild(self, links, blocks):
        for it in self._link_items + self._block_items:
            self.removeItem(it)
        self._link_items, self._block_items = [], []
        for keys in links:
            is_coupler = self.drawing is not None and tuple(keys) == tuple(self.drawing.coupler)
            color = COUPLER if is_coupler else LINK
            if len(keys) > 2:
                item = QtWidgets.QGraphicsPolygonItem()
                c = QtGui.QColor(color)
                item.setPen(pg.mkPen(color, width=3))
                c.setAlpha(60)
                item.setBrush(QtGui.QBrush(c))
            else:
                item = pg.PlotDataItem(pen=pg.mkPen(color, width=5))
            item.setZValue(10)
            self.addItem(item)
            self._link_items.append(item)
        for _ in blocks:
            item = pg.PlotDataItem(pen=pg.mkPen(LINK, width=2), fillLevel=None)
            item.setZValue(12)
            self.addItem(item)
            self._block_items.append(item)

    def _draw_static(self):
        f = self.circuit.frames
        P = f.points[self.drawing.tracer]
        self.curve.setData(*self._xy(np.append(P, P[:1])))
        for it in self.other_curves + self.rail_items:
            self.removeItem(it)
        self.other_curves, self.rail_items = [], []
        for other in self._others:
            Q = other.points[self.drawing.tracer]
            item = pg.PlotDataItem(*self._xy(np.append(Q, Q[:1])),
                                   pen=pg.mkPen(CURVE_OTHER + "55", width=1, style=QtCore.Qt.DashLine))
            self.addItem(item)
            self.other_curves.append(item)
        for c, ang, half in self.drawing.rails:
            d = half * np.exp(1j * ang)
            item = pg.PlotDataItem(*self._xy(np.array([c - d, c + d])),
                                   pen=pg.mkPen(GROUND, width=2, style=QtCore.Qt.DashLine))
            self.addItem(item)
            self.rail_items.append(item)
        g = [f.points[k][0] for k in self.drawing.ground]
        self.ground_marks.setData(*self._xy(np.array(g, complex)))
        t = [P[i] for i in self._toggles]
        self.toggle_marks.setData(*self._xy(np.array(t, complex)))

    def show_frame(self, i):
        if self.circuit is None:
            return
        p = {k: v[i] for k, v in self.circuit.frames.points.items()}
        for keys, item in zip(self.drawing.links, self._link_items):
            x, y = self._xy(np.array([p[k] for k in keys]))
            if isinstance(item, QtWidgets.QGraphicsPolygonItem):
                item.setPolygon(QtGui.QPolygonF([QtCore.QPointF(a, b) for a, b in zip(x, y)]))
            else:
                item.setData(x, y)
        s = 0.05 * self.mech.scale()
        for (key, orient), item in zip(self.drawing.blocks, self._block_items):
            u = p[orient] if isinstance(orient, str) else np.exp(1j * orient)
            corners = p[key] + np.array([1.6 + 1j, -1.6 + 1j, -1.6 - 1j, 1.6 - 1j, 1.6 + 1j]) * s * u
            item.setData(*self._xy(corners))
        self.pins.setData(*self._xy(np.array([p[k] for k in self.drawing.pins + self.drawing.ground], complex)))
        self.tracer.setData(*self._xy(np.array([p[self.drawing.tracer]])))
