"""Timeline strip: one input cycle (0-360 deg) with a marker per keyframe.

Hollow markers are free timing (the solver decides); solid ones are
prescribed. Drag a marker to prescribe its timing; right-click for
free / absolute / relative. The playhead shows the current input angle."""

import math

from PySide6 import QtCore, QtGui, QtWidgets

FREE = QtGui.QColor("#b39ddb")
FIXED = QtGui.QColor("#ffd54f")
PLAYHEAD = QtGui.QColor("#f0a04b")


def resolved_times(keyframes):
    """Input angle (rad) for every keyframe, or None for free ones."""
    out, prev = [], None
    for k in keyframes:
        if k.timing == "absolute":
            prev = k.t
        elif k.timing == "relative" and prev is not None:
            prev = prev + k.t
        else:
            prev = None if k.timing == "free" else prev
            out.append(None)
            continue
        out.append(prev)
    return out


def display_times(keyframes):
    """Resolved times, with free keyframes spread evenly between their
    prescribed neighbours (for display only)."""
    t = resolved_times(keyframes)
    n = len(t)
    full = 2 * math.pi
    out = list(t)
    i = 0
    while i < n:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < n and out[j] is None:
            j += 1
        a = out[i - 1] if i > 0 else None
        b = out[j] if j < n else None
        if a is None and b is None:
            a, b = 0.0, full
            span = [(k + 0.5) / (j - i) for k in range(j - i)]
        else:
            a = a if a is not None else (b - (j - i + 1) * 0.35 if b is not None else 0.0)
            b = b if b is not None else a + (j - i + 1) * 0.35
            span = [(k + 1) / (j - i + 1) for k in range(j - i)]
        for k, f in zip(range(i, j), span):
            out[k] = a + f * (b - a)
        i = j
    return out


class Timeline(QtWidgets.QWidget):
    def __init__(self, doc):
        super().__init__()
        self.doc = doc
        self.playhead = None
        self.drag = None
        self.setMinimumHeight(46)
        self.setMouseTracking(True)
        self.setToolTip("Keyframe timing over one input revolution. Drag a marker to prescribe its timing; "
                        "right-click to make it free / absolute / relative.")
        doc.changed.connect(self.update)
        doc.selectionChanged.connect(self.update)

    # --- geometry --------------------------------------------------------
    def _bar(self):
        m = 14
        return QtCore.QRectF(m, 16, self.width() - 2 * m, 12)

    def _x(self, ang):
        r = self._bar()
        return r.left() + (ang % (2 * math.pi)) / (2 * math.pi) * r.width()

    def _ang(self, x):
        r = self._bar()
        return min(max((x - r.left()) / r.width(), 0.0), 1.0) * 2 * math.pi

    def _marker_at(self, x):
        best = None
        for i, a in enumerate(display_times(self.doc.target.keyframes)):
            d = abs(self._x(a) - x)
            if d < 8 and (best is None or d < best[0]):
                best = (d, i)
        return None if best is None else best[1]

    def set_playhead(self, ang):
        self.playhead = ang
        self.update()

    # --- painting --------------------------------------------------------
    def paintEvent(self, _):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = self.palette()
        r = self._bar()
        p.setPen(QtGui.QPen(pal.color(QtGui.QPalette.Mid)))
        p.setBrush(pal.color(QtGui.QPalette.Base))
        p.drawRoundedRect(r, 4, 4)
        f = p.font()
        f.setPointSizeF(max(6.0, f.pointSizeF() - 1.5))
        p.setFont(f)
        p.setPen(pal.color(QtGui.QPalette.PlaceholderText))
        for deg in range(0, 361, 30):
            x = r.left() + deg / 360 * r.width()
            p.drawLine(QtCore.QPointF(x, r.bottom()), QtCore.QPointF(x, r.bottom() + 3))
            p.drawText(QtCore.QRectF(x - 20, r.bottom() + 3, 40, 14), QtCore.Qt.AlignCenter, f"{deg}°")
        ks = self.doc.target.keyframes
        for i, (k, a) in enumerate(zip(ks, display_times(ks))):
            x = self._x(a)
            color = FIXED if k.timing != "free" else FREE
            sel = k.id == self.doc.selected
            p.setPen(QtGui.QPen(QtGui.QColor("#ffffff") if sel else color, 2 if sel else 1.5))
            p.setBrush(color if k.timing != "free" else QtCore.Qt.NoBrush)
            p.drawEllipse(QtCore.QPointF(x, r.center().y()), 5, 5)
            p.setPen(color)
            p.drawText(QtCore.QRectF(x - 12, 0, 24, 15), QtCore.Qt.AlignCenter,
                       str(i + 1) + ("r" if k.timing == "relative" else ""))
        if self.playhead is not None:
            x = self._x(self.playhead)
            p.setPen(QtGui.QPen(PLAYHEAD, 2))
            p.drawLine(QtCore.QPointF(x, r.top() - 4), QtCore.QPointF(x, r.bottom() + 4))
        p.end()

    # --- interaction -----------------------------------------------------
    def mousePressEvent(self, ev):
        i = self._marker_at(ev.position().x())
        if i is None:
            return
        kid = self.doc.target.keyframes[i].id
        self.doc.select(kid)
        if ev.button() == QtCore.Qt.RightButton:
            self._menu(i, ev.globalPosition().toPoint())
        else:
            self.drag = (kid, self.doc.new_merge_key())

    def mouseMoveEvent(self, ev):
        if not self.drag:
            return
        kid, key = self.drag
        step = math.radians(5 if ev.modifiers() & QtCore.Qt.ShiftModifier else 1)
        ang = round(self._ang(ev.position().x()) / step) * step
        i = self.doc.target.index_of(kid)
        prev = resolved_times(self.doc.target.keyframes)[i - 1] if i > 0 else None

        def fn(t):
            k = t.keyframe(kid)
            if k.timing == "relative" and prev is not None:
                k.t = ang - prev
            else:
                k.timing, k.t = "absolute", ang
        self.doc.edit("Set timing", fn, key)

    def mouseReleaseEvent(self, ev):
        self.drag = None

    def _menu(self, i, where):
        k = self.doc.target.keyframes[i]
        menu = QtWidgets.QMenu(self)
        acts = {}
        for mode, label in (("free", "Free timing (solver decides)"), ("absolute", "Prescribed input angle"),
                            ("relative", "Relative to previous keyframe")):
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(k.timing == mode)
            a.setEnabled(not (mode == "relative" and i == 0))
            acts[a] = mode
        chosen = menu.exec(where)
        if chosen in acts:
            self.set_mode(k.id, acts[chosen])

    def set_mode(self, kid, mode):
        ks = self.doc.target.keyframes
        i = self.doc.target.index_of(kid)
        shown = display_times(ks)[i]
        prev = resolved_times(ks)[i - 1] if i > 0 else None

        def fn(t):
            k = t.keyframe(kid)
            k.timing = mode
            if mode == "absolute":
                k.t = shown % (2 * math.pi)
            elif mode == "relative":
                k.t = shown - (prev if prev is not None else display_times(ks)[i - 1])
        self.doc.edit("Change timing mode", fn)
