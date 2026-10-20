"""Canvas overlay for 4 and 5 poses: the center-point curve (where ground
pivots can go), its circle-point curve (the matching moving pivots), the
Burmester points, and the slider options.

The stretches of the center-point curve used by at least one valid design
are drawn thick and green, so you can see the usable parts before clicking.
Coordinates in are mm; the view works in display units."""

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore

from kinsyn.synthesis.motion import Options

CENTER = "#ffb74d"
CIRCLE = "#80cbc4"
USABLE = "#66bb6a"
POINT = "#ffd54f"
SLIDER = "#f48fb1"


def _join(lines):
    """Polylines into one NaN-separated array (one plot item)."""
    if not lines:
        return np.array([], complex)
    return np.concatenate([np.append(np.asarray(l, complex), complex(np.nan, np.nan)) for l in lines])


class BurmesterLayer:
    def __init__(self, view):
        self.view = view
        self.visible = True
        self.result = self.poses = None
        self.center = pg.PlotDataItem(pen=pg.mkPen(CENTER, width=1.5), connect="finite")
        self.usable = pg.PlotDataItem(pen=pg.mkPen(USABLE, width=4), connect="finite")
        self.circle = pg.PlotDataItem(pen=pg.mkPen(CIRCLE, width=1.2, style=QtCore.Qt.DashLine), connect="finite")
        self.points = pg.ScatterPlotItem(symbol="star", size=18, pen=pg.mkPen("#15171c", width=1),
                                         brush=pg.mkBrush(POINT))
        self.sliders = pg.PlotDataItem(pen=pg.mkPen(SLIDER, width=1.5, style=QtCore.Qt.DashDotLine),
                                       connect="finite")
        self.slider_pts = pg.ScatterPlotItem(symbol="s", size=10, pen=pg.mkPen(SLIDER, width=2), brush=None)
        self.items = [self.center, self.circle, self.usable, self.sliders, self.slider_pts, self.points]
        for z, it in zip((32, 31, 33, 34, 35, 36), self.items):
            it.setZValue(z)
            view.addItem(it)

    def _xy(self, z):
        z = np.asarray(z, complex) / self.view.factor
        return z.real, z.imag

    def set_visible(self, on):
        self.visible = on
        for it in self.items:
            it.setVisible(on)

    def set_result(self, res, poses=None):
        """Draw `res` (a motion.Result). `poses` (dyad.Poses) places the
        slider options; None clears the overlay."""
        self.result, self.poses = res, poses
        empty = res is None or not res.curves
        if empty:
            for it in self.items:
                it.setData([], [])
            return
        center = [l for c in res.curves for l in c.center]
        circle = [l for c in res.curves[:1] for l in c.circle]
        self.center.setData(*self._xy(_join(center)))
        self.circle.setData(*self._xy(_join(circle)))
        self.usable.setData(*self._xy(_join(self._usable(center, res))))
        self.points.setData(*self._xy(res.burmester_points))
        self._draw_sliders(res, poses)

    def _usable(self, center, res):
        """Parts of the center-point curve near a ground pivot of a valid design."""
        grounds = np.array([d.G for c in res.solutions for d in c.dyads if d.kind == "RR"], complex)
        if not len(grounds) or len(res.burmester_points):
            return []
        total = sum(float(np.abs(np.diff(l)).sum()) for l in center)
        # Just over the spacing of the solver's samples, so neighbours join up.
        reach = 1.1 * total / Options.curve_samples
        out = []
        for line in center:
            near = np.abs(line[:, None] - grounds[None, :]).min(axis=1) <= reach
            out.append(np.where(near, line, complex(np.nan, np.nan)))
        return out

    def _draw_sliders(self, res, poses):
        lines, pts = [], []
        if poses is not None:
            from kinsyn.synthesis.dyad import pr_from_direction, rp_from_direction

            span = poses.scale()
            for g in res.slider_dirs.get("PR", []):
                d = pr_from_direction(poses, g)
                if d is not None:
                    M = poses.world(d.m)  # the Ball point's positions, all on the rail
                    u = np.exp(1j * g)
                    t = ((M - M[0]) / u).real
                    lines.append([M[0] + (t.min() - 0.3 * span) * u, M[0] + (t.max() + 0.3 * span) * u])
                    pts += list(M)
            for phi in res.slider_dirs.get("RP", []):
                d = rp_from_direction(poses, phi)
                if d is not None:
                    pts.append(d.G)  # the swivel
        self.sliders.setData(*self._xy(_join(lines)))
        self.slider_pts.setData(*self._xy(pts))

    def snap_geometry(self):
        """(polylines, points) for snapping: the center-point curves and the
        Burmester points."""
        if not self.visible or self.result is None or not self.result.curves:
            return [], []
        return [l for c in self.result.curves for l in c.center], list(self.result.burmester_points)
