"""Generate app screenshots for the help docs (runs the real app offscreen).

    XDG_CONFIG_HOME=$(mktemp -d) XDG_STATE_HOME=$(mktemp -d) \\
        QT_QPA_PLATFORM=offscreen .venv/bin/python tools/make_screenshots.py

Uses the Fusion style with a fixed dark palette, so the images look the same
whatever desktop theme they are generated on."""

import math
import sys
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

OUT = Path(__file__).resolve().parents[1] / "kinsyn/help/docs/img"
CALLOUT = QtGui.QColor("#f0a04b")


def dark_palette():
    p = QtGui.QPalette()
    c = QtGui.QColor
    for role, col in ((QtGui.QPalette.Window, "#1f2228"), (QtGui.QPalette.WindowText, "#d6dae0"),
                      (QtGui.QPalette.Base, "#16181d"), (QtGui.QPalette.AlternateBase, "#23262d"),
                      (QtGui.QPalette.Text, "#d6dae0"), (QtGui.QPalette.Button, "#2a2e36"),
                      (QtGui.QPalette.ButtonText, "#d6dae0"), (QtGui.QPalette.Highlight, "#3b6ea8"),
                      (QtGui.QPalette.HighlightedText, "#ffffff"), (QtGui.QPalette.ToolTipBase, "#2a2e36"),
                      (QtGui.QPalette.ToolTipText, "#d6dae0"), (QtGui.QPalette.PlaceholderText, "#7d8590"),
                      (QtGui.QPalette.Mid, "#3a3f48"), (QtGui.QPalette.Link, "#6cb4ff")):
        p.setColor(role, c(col))
    return p


def callouts(img, window, marks):
    """Draw numbered circles at widget positions on a window grab."""
    painter = QtGui.QPainter(img)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    f = QtGui.QFont()
    f.setPointSizeF(13)
    f.setBold(True)
    painter.setFont(f)
    dpr = img.devicePixelRatio()
    for n, widget, rel in marks:
        top_left = widget.mapTo(window, QtCore.QPoint(0, 0))
        x = top_left.x() + rel[0] * widget.width()
        y = top_left.y() + rel[1] * widget.height()
        r = 15
        painter.setPen(QtGui.QPen(QtGui.QColor("#15171c"), 3))
        painter.setBrush(CALLOUT)
        painter.drawEllipse(QtCore.QPointF(x, y) / 1.0, r, r)
        painter.setPen(QtGui.QColor("#15171c"))
        painter.drawText(QtCore.QRectF(x - r, y - r, 2 * r, 2 * r), QtCore.Qt.AlignCenter, str(n))
    painter.end()
    return img


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    pg.setConfigOptions(antialias=True, background="#15171c", foreground="#c8d0dc")
    from kinsyn.core.target import Body, Keyframe
    from kinsyn.gui.main_window import MainWindow

    w = MainWindow()
    w.resize(1500, 920)
    w.show()
    for _ in range(5):
        app.processEvents()
    entry = next(e for e in w.library.entries if e.id == "crank_rocker")
    w.load_entry(entry)
    w.seek(120)

    def fill(t):
        t.keyframes = [Keyframe(-40 + 70j, 0.0), Keyframe(10 + 100j, math.radians(25)),
                       Keyframe(70 + 110j, math.radians(60))]
        t.body = Body([[-12 - 6j, 22 - 6j, 22 + 7j, -12 + 7j]])
    w.doc.edit("Tutorial poses", fill)
    w.view.setRange(xRange=(-70, 150), yRange=(-30, 140), padding=0)
    w.set_tool("pose")
    w.set_prompt(w.tools["pose"].prompt)
    for _ in range(10):
        app.processEvents()

    img = w.grab().toImage()
    tb = w.findChild(QtWidgets.QToolBar, "Tools")
    marks = [(1, tb, (0.5, 0.40)), (2, w.library, (0.8, 0.62)), (3, w.view, (0.55, 0.12)),
             (4, w.target_panel, (0.93, 0.62)), (5, w.timeline, (0.03, 0.3)), (6, w.plots, (0.97, 0.1)),
             (7, w.statusBar(), (0.35, 0.5))]
    callouts(img, w, marks).save(str(OUT / "tour.png"))
    print("wrote", OUT / "tour.png")

    # Synthesis tab with a design picked for the same three poses.
    import time
    w.set_tool("select")
    w.synth_dock.raise_()
    w.synth.solve()
    t0 = time.time()
    while (w.synth.result is None or not w.synth.result.evaluated) and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.01)
    w.synth.table.selectRow(next(i for i, c in enumerate(w.synth.rows) if c.family == "fourbar"))
    w.seek(len(w.circuit.q) // 3)
    for _ in range(10):
        app.processEvents()
    img = w.grab().toImage()
    marks = [(1, w.synth.method, (0.9, 0.5)), (2, w.synth.input_motion, (0.97, 0.5)),
             (3, w.synth.tabs, (0.97, 0.5)), (4, w.synth.table, (0.97, 0.12)),
             (5, w.synth.fix_btn, (0.05, 0.5)), (6, w.view, (0.5, 0.08))]
    callouts(img, w, marks).save(str(OUT / "synthesis.png"))
    print("wrote", OUT / "synthesis.png")

    # Four poses: the Burmester curves on the canvas.
    def fill4(t):
        t.keyframes.append(Keyframe(120 + 90j, math.radians(95)))
    w.doc.edit("Fourth pose", fill4)
    w.synth.solve()
    t0 = time.time()
    while (w.synth.result is None or not w.synth.result.curves or not w.synth.result.evaluated) \
            and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.01)
    w.synth.table.selectRow(next(i for i, c in enumerate(w.synth.rows) if c.family == "fourbar"))
    w.view.autorange()
    for _ in range(10):
        app.processEvents()
    res = w.synth.result
    img = w.grab().toImage()

    def on_canvas(z):
        """(widget, relative position) of a point in mm on the canvas."""
        vb = w.view.getViewBox()
        sp = vb.mapViewToScene(QtCore.QPointF(z.real / w.view.factor, z.imag / w.view.factor))
        vp = w.view.mapFromScene(sp)
        return w.view, (vp.x() / w.view.width(), vp.y() / w.view.height())

    xr, yr = w.view.getViewBox().viewRange()
    inside = lambda z: xr[0] < z.real < xr[1] and yr[0] < z.imag < yr[1]
    centre = next(z for line in res.curves[0].center for z in line[len(line) // 3:] if inside(z))
    circle = next(z for line in res.curves[0].circle for z in line[len(line) // 2:] if np.isfinite(z) and inside(z))
    gx, gy = w.burmester.usable.getData()
    usable = (gx + 1j * gy) * w.view.factor
    green = next(z for z in usable if np.isfinite(z) and inside(z))
    marks = [(1, *on_canvas(centre)), (2, *on_canvas(circle)), (3, *on_canvas(green)),
             (4, w.synth.show_curves, (0.97, 0.5)), (5, w.synth.legend, (0.97, 0.85))]
    callouts(img, w, marks).save(str(OUT / "burmester.png"))
    print("wrote", OUT / "burmester.png")


if __name__ == "__main__":
    main()
