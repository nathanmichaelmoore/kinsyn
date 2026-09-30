"""Canvas tools for editing the target. All positions are mm (complex).

Each tool gets mouse events already mapped to model coordinates, plus typed
input from the command line ("x, y", "x, y, angle", "@dx, dy" relative)."""

import cmath
import math

import numpy as np
from PySide6 import QtCore, QtWidgets

from kinsyn.core.snap import SnapResult, nice_step, snap_point
from kinsyn.core.target import Body, Keyframe, pose_inverse
from kinsyn.core.units import parse_angle, parse_length

ANGLE_STEP = math.radians(15)
SNAP_PX = 10
GRID_PX = 14
DRAG_ANGLE_MIN_PX = 6


def parse_coords(text, unit, last=None):
    """'x, y[, angle]' or '@dx, dy[, dangle]' relative to `last`
    ((pos, angle) or None). Returns (pos, angle or None)."""
    s = text.strip()
    rel = s.startswith("@")
    parts = [p for p in s.lstrip("@").replace(";", ",").split(",")]
    if len(parts) not in (2, 3):
        raise ValueError("expected x, y or x, y, angle")
    x, y = parse_length(parts[0], unit), parse_length(parts[1], unit)
    ang = parse_angle(parts[2]) if len(parts) == 3 else None
    if rel:
        if last is None:
            raise ValueError("nothing to be relative to yet")
        return last[0] + complex(x, y), (last[1] + ang if ang is not None else None)
    return complex(x, y), ang


class EditorContext:
    """What tools need from the window."""

    def __init__(self, window):
        self.w = window
        self.snapping = True

    @property
    def doc(self):
        return self.w.doc

    @property
    def layer(self):
        return self.w.layer

    @property
    def unit(self):
        return self.w.unit

    def set_prompt(self, text):
        self.w.set_prompt(text)

    def modifiers(self):
        return QtWidgets.QApplication.keyboardModifiers()

    def snap_points(self, exclude=None):
        t = self.doc.target
        pts = [k.pos for k in t.keyframes if k.id != exclude]
        if t.body is not None:
            for k in t.keyframes[:1]:
                pts += [p for pl in t.body.at(k.pos, k.angle) for p in pl]
        for c in t.curves:
            pts += list(c.points)
        pts += [p.pos for p in t.pivots]
        pts += self.w.mechanism_snap_points()
        return pts

    def snap(self, p, ref=None, exclude=None):
        mods = self.modifiers()
        if not self.snapping or mods & QtCore.Qt.AltModifier:
            return SnapResult(p)
        mpp = self.layer.mm_per_px()
        angle_step = ANGLE_STEP if (ref is not None and mods & QtCore.Qt.ShiftModifier) else None
        return snap_point(p, tol=SNAP_PX * mpp, points=self.snap_points(exclude),
                          grid_step=nice_step(GRID_PX * mpp, self.unit), ref=ref, angle_step=angle_step)

    def snap_angle(self, ang):
        if self.modifiers() & QtCore.Qt.ShiftModifier:
            return round(ang / ANGLE_STEP) * ANGLE_STEP
        return ang

    def last_pose(self):
        ks = self.doc.target.keyframes
        return (ks[-1].pos, ks[-1].angle) if ks else None


class Tool:
    name = ""
    prompt = ""
    cursor = QtCore.Qt.ArrowCursor

    def __init__(self, ctx):
        self.ctx = ctx

    def activate(self):
        self.ctx.set_prompt(self.prompt)
        self.ctx.w.view.setCursor(self.cursor)

    def deactivate(self):
        self.ctx.layer.clear_feedback()

    def hover(self, p):
        self.ctx.layer.show_snap(self.ctx.snap(p, ref=self._ref()))

    def _ref(self):
        last = self.ctx.last_pose()
        return last[0] if last else None

    def click(self, p, ev):
        return False

    def drag_start(self, p, ev):
        return False

    def drag_move(self, p, ev):
        pass

    def drag_end(self, p, ev):
        pass

    def key(self, key):
        return False

    def text(self, s):
        return False


class SelectTool(Tool):
    name = "select"
    prompt = "Select: click a keyframe, drag its dot to move, drag its arrow tip to rotate · type x, y[, angle] to move the selected one"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.drag = None

    def hover(self, p):
        hit = self.ctx.layer.hit(p)
        view = self.ctx.w.view
        view.setCursor(QtCore.Qt.PointingHandCursor if hit else QtCore.Qt.ArrowCursor)

    def click(self, p, ev):
        hit = self.ctx.layer.hit(p)
        self.ctx.doc.select(hit[1] if hit else None)
        return True

    def drag_start(self, p, ev):
        hit = self.ctx.layer.hit(p)
        if not hit:
            return False  # let the view pan
        self.ctx.doc.select(hit[1])
        self.drag = (hit[0], hit[1], self.ctx.doc.new_merge_key())
        return True

    def drag_move(self, p, ev):
        if not self.drag:
            return
        what, kid, key = self.drag
        k = self.ctx.doc.target.keyframe(kid)
        if what == "pos":
            r = self.ctx.snap(p, exclude=kid)
            self.ctx.layer.show_snap(r)
            self.ctx.doc.edit("Move keyframe", lambda t: setattr(t.keyframe(kid), "pos", r.point), key)
        else:
            ang = self.ctx.snap_angle(cmath.phase(p - k.pos))
            self.ctx.doc.edit("Rotate pose", lambda t: setattr(t.keyframe(kid), "angle", ang), key)

    def drag_end(self, p, ev):
        self.drag = None
        self.ctx.layer.clear_feedback()

    def text(self, s):
        k = self.ctx.doc.selected_keyframe()
        if k is None:
            raise ValueError("select a keyframe first")
        pos, ang = parse_coords(s, self.ctx.unit, (k.pos, k.angle))

        def fn(t):
            kk = t.keyframe(k.id)
            kk.pos = pos
            if ang is not None:
                kk.angle = ang
        self.ctx.doc.edit("Move keyframe", fn)
        return True


class PoseTool(Tool):
    """Click to place, or press-drag to place and aim. In path mode (or as
    the Point tool) orientation is ignored."""

    name = "pose"
    prompt = "Pose: click to place, drag to set its angle (Shift: 15° steps, Alt: no snap) · or type x, y[, angle]"
    cursor = QtCore.Qt.CrossCursor

    def __init__(self, ctx, with_angle=True):
        super().__init__(ctx)
        self.with_angle = with_angle
        if not with_angle:
            self.name = "point"
            self.prompt = "Point: click to place (Shift: 15° from last point, Alt: no snap) · or type x, y"
        self.anchor = None

    def _default_angle(self):
        last = self.ctx.last_pose()
        return last[1] if last else 0.0

    def _commit(self, pos, angle):
        k = Keyframe(pos=pos, angle=self._default_angle() if angle is None else angle)
        self.ctx.doc.edit("Add pose" if self.with_angle else "Add point", lambda t: t.keyframes.append(k))
        self.ctx.doc.select(k.id)

    def click(self, p, ev):
        self._commit(self.ctx.snap(p, ref=self._ref()).point, None)
        return True

    def drag_start(self, p, ev):
        self.anchor = self.ctx.snap(p, ref=self._ref()).point
        return True

    def _aim(self, p):
        v = p - self.anchor
        if not self.with_angle or abs(v) < DRAG_ANGLE_MIN_PX * self.ctx.layer.mm_per_px():
            return None
        return self.ctx.snap_angle(cmath.phase(v))

    def drag_move(self, p, ev):
        ang = self._aim(p)
        if ang is None:
            self.ctx.layer.show_preview(points=[self.anchor])
        else:
            tip = self.anchor + abs(p - self.anchor) * cmath.exp(1j * ang)
            self.ctx.layer.show_preview(line=[self.anchor, tip], points=[self.anchor])

    def drag_end(self, p, ev):
        self._commit(self.anchor, self._aim(p))
        self.anchor = None
        self.ctx.layer.clear_feedback()

    def text(self, s):
        pos, ang = parse_coords(s, self.ctx.unit, self.ctx.last_pose())
        self._commit(pos, ang)
        return True


class BodyTool(Tool):
    """Click the outline of the moving part; double-click or Enter to
    finish, Backspace to remove the last point, Esc to cancel."""

    name = "body"
    prompt = "Body: click outline points of the moving part · double-click / Enter to finish · Backspace undoes a point · Esc cancels"
    cursor = QtCore.Qt.CrossCursor

    def __init__(self, ctx):
        super().__init__(ctx)
        self.pts = []

    def deactivate(self):
        self.pts = []
        super().deactivate()

    def _ref(self):
        return self.pts[-1] if self.pts else None

    def hover(self, p):
        r = self.ctx.snap(p, ref=self._ref())
        self.ctx.layer.show_snap(r)
        if self.pts:
            self.ctx.layer.show_preview(line=self.pts + [r.point], points=self.pts)

    def click(self, p, ev):
        if ev is not None and ev.double():
            self.finish()
            return True
        self.pts.append(self.ctx.snap(p, ref=self._ref()).point)
        self.ctx.layer.show_preview(line=self.pts, points=self.pts)
        return True

    def key(self, key):
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.finish()
        elif key == QtCore.Qt.Key_Escape:
            self.pts = []
            self.ctx.layer.clear_feedback()
        elif key == QtCore.Qt.Key_Backspace and self.pts:
            self.pts.pop()
            self.ctx.layer.show_preview(line=self.pts, points=self.pts)
        else:
            return False
        return True

    def text(self, s):
        last = (self.pts[-1], 0.0) if self.pts else None
        pos, _ = parse_coords(s, self.ctx.unit, last)
        self.pts.append(pos)
        self.ctx.layer.show_preview(line=self.pts, points=self.pts)
        return True

    def finish(self):
        # Drop a duplicate final point (from the double-click's first click).
        pts = list(self.pts)
        if len(pts) >= 2 and abs(pts[-1] - pts[-2]) < 1e-9:
            pts.pop()
        self.pts = []
        self.ctx.layer.clear_feedback()
        if len(pts) < 2:
            return
        closed = len(pts) >= 3

        def fn(t):
            if t.keyframes:
                ref = t.keyframes[0]
            else:
                c = complex(np.mean(pts))
                ref = Keyframe(pos=c, angle=0.0)
                t.keyframes.append(ref)
            t.body = Body([list(pose_inverse(pts, ref.pos, ref.angle))], closed=closed)
        self.ctx.doc.edit("Set body outline", fn)
