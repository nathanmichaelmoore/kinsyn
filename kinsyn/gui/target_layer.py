"""Draws the target (poses as ghost bodies or arrows, points, body outline,
sequence line) plus tool feedback (snap marker, guides, previews) on top of
the mechanism view. Coordinates in are mm; the view works in display units."""

import math

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

GHOST = "#b39ddb"
SELECTED = "#ffd54f"
WARN = "#ef5350"
SNAP = "#66bb6a"
PREVIEW = "#80cbc4"

ARROW_PX = 46  # pose arrow / rotation handle distance, screen pixels


class TargetLayer(QtCore.QObject):
    def __init__(self, view, doc):
        super().__init__()
        self.view, self.doc = view, doc
        self.items = []  # per-redraw items
        self.labels = []
        self.show_ghosts = True
        # Persistent feedback items.
        self.snap_marker = pg.ScatterPlotItem(size=12, symbol="s", pen=pg.mkPen(SNAP, width=2), brush=None)
        self.snap_text = pg.TextItem(color=SNAP, anchor=(-0.15, 1.2))
        self.guides = []
        self.preview = pg.PlotDataItem(pen=pg.mkPen(PREVIEW, width=2, style=QtCore.Qt.DashLine))
        self.preview_pts = pg.ScatterPlotItem(size=8, pen=pg.mkPen(PREVIEW), brush=pg.mkBrush(PREVIEW))
        for it in (self.snap_marker, self.snap_text, self.preview, self.preview_pts):
            it.setZValue(60)
            view.addItem(it)
        doc.changed.connect(self.redraw)
        doc.selectionChanged.connect(self.redraw)
        view.getViewBox().sigRangeChanged.connect(lambda *_: self.redraw())

    # --- helpers ---------------------------------------------------------
    def mm_per_px(self):
        px = self.view.getViewBox().viewPixelSize()
        return max(px[0], px[1]) * self.view.factor

    def _xy(self, z):
        z = np.asarray(z, complex) / self.view.factor
        return z.real, z.imag

    def _add(self, item, z=40):
        item.setZValue(z)
        self.view.addItem(item)
        self.items.append(item)
        return item

    def handle_radius(self):
        return ARROW_PX * self.mm_per_px()

    def hit(self, p, tol_px=9):
        """What is under point p (mm)? ("rot", id) | ("pos", id) | None."""
        tol = tol_px * self.mm_per_px()
        R = self.handle_radius()
        best = None
        for k in self.doc.target.keyframes:
            if self.doc.target.mode == "motion":
                d = abs(k.pos + R * complex(math.cos(k.angle), math.sin(k.angle)) - p)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, "rot", k.id)
            d = abs(k.pos - p)
            if d <= tol and (best is None or d < best[0]):
                best = (d, "pos", k.id)
        return None if best is None else best[1:]

    # --- drawing ---------------------------------------------------------
    def redraw(self):
        for it in self.items:
            self.view.removeItem(it)
        self.items = []
        t = self.doc.target
        if not t.keyframes and t.body is None:
            return
        warned = {i for i, _ in t.warnings() if i is not None}
        R = self.handle_radius()
        motion = t.mode == "motion"

        if len(t.keyframes) > 1:
            seq = np.array([k.pos for k in t.keyframes])
            self._add(pg.PlotDataItem(*self._xy(seq), pen=pg.mkPen(GHOST + "70", width=1,
                                                                     style=QtCore.Qt.DotLine)), 35)

        pos_pts, pos_brush, rot_pts = [], [], []
        for i, k in enumerate(t.keyframes):
            sel = k.id == self.doc.selected
            color = SELECTED if sel else (WARN if i in warned else GHOST)
            u = complex(math.cos(k.angle), math.sin(k.angle))
            if motion:
                if t.body is not None and self.show_ghosts:
                    for pl in t.body.at(k.pos, k.angle):
                        pts = np.append(pl, pl[:1]) if t.body.closed else pl
                        self._add(pg.PlotDataItem(*self._xy(pts), pen=pg.mkPen(color + ("ff" if sel else "a0"),
                                                                                   width=2 if sel else 1.5),
                                                  fillLevel=None), 41 if sel else 40)
                # Orientation arrow (also the rotation handle).
                tip = k.pos + R * u
                head = [tip - 0.28 * R * u * complex(math.cos(a), math.sin(a)) for a in (0.45, -0.45)]
                self._add(pg.PlotDataItem(*self._xy([k.pos, tip, head[0], tip, head[1]]),
                                          pen=pg.mkPen(color, width=2)), 42)
                rot_pts.append(tip)
            if k.tol > 0:
                c = k.pos + k.tol * np.exp(1j * np.linspace(0, 2 * np.pi, 64))
                self._add(pg.PlotDataItem(*self._xy(c), pen=pg.mkPen(color, width=1, style=QtCore.Qt.DashLine)), 39)
            pos_pts.append(k.pos)
            pos_brush.append(pg.mkBrush(color))
            label = pg.TextItem(str(i + 1), color=color, anchor=(1.3, 1.3))
            label.setPos(*[v[0] for v in self._xy([k.pos])])
            self._add(label, 43)

        if pos_pts:
            self._add(pg.ScatterPlotItem(*self._xy(pos_pts), size=11, symbol="o", brush=pos_brush,
                                         pen=pg.mkPen("#15171c", width=1.5)), 44)
        if rot_pts:
            self._add(pg.ScatterPlotItem(*self._xy(rot_pts), size=9, symbol="d",
                                         brush=pg.mkBrush("#15171c"), pen=pg.mkPen(GHOST, width=1.5)), 44)

    # --- tool feedback ---------------------------------------------------
    def show_snap(self, result):
        for g in self.guides:
            self.view.removeItem(g)
        self.guides = []
        if result is None or result.kind in (None,):
            self.snap_marker.setData([])
            self.snap_text.setText("")
            return
        self.snap_marker.setData(*self._xy([result.point]))
        self.snap_text.setText(result.label if result.kind in ("object", "angle", "align") else "")
        self.snap_text.setPos(*[v[0] for v in self._xy([result.point])])
        for a, b in result.guides:
            g = pg.PlotDataItem(*self._xy([a, b]), pen=pg.mkPen(SNAP + "aa", width=1, style=QtCore.Qt.DashLine))
            g.setZValue(59)
            self.view.addItem(g)
            self.guides.append(g)

    def show_preview(self, line=None, points=None):
        self.preview.setData(*self._xy(line) if line is not None and len(line) else ([], []))
        self.preview_pts.setData(*self._xy(points) if points is not None and len(points) else ([], []))

    def clear_feedback(self):
        self.show_snap(None)
        self.show_preview()
