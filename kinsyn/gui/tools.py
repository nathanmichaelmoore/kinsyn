"""Canvas tools for editing the target. All positions are mm (complex).

Each tool gets mouse events already mapped to model coordinates, plus typed
input from the command line ("x, y", "x, y, angle", "@dx, dy" relative)."""

import cmath
import math

import numpy as np
from PySide6 import QtCore, QtWidgets

from kinsyn.core.snap import SnapResult, nice_step, snap_point
from kinsyn.core.target import Body, Curve, FixedPivot, Keyframe, Zone, pose_inverse, resample_even, simplify
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

    def right_click(self, p, ev):
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

    def _hit(self, p):
        return self.ctx.layer.hit(p) or self.ctx.layer.hit_items(p)

    def hover(self, p):
        view = self.ctx.w.view
        view.setCursor(QtCore.Qt.PointingHandCursor if self._hit(p) else QtCore.Qt.ArrowCursor)

    def _select(self, hit):
        doc = self.ctx.doc
        if hit is None:
            doc.select(None)
            doc.select_item(None)
        elif hit[0] in ("pos", "rot"):
            doc.select(hit[1])
        else:
            doc.select_item(hit)

    def click(self, p, ev):
        self._select(self._hit(p))
        return True

    def drag_start(self, p, ev):
        hit = self._hit(p)
        if not hit:
            return False  # let the view pan
        self._select(hit)
        self.drag = (hit, self.ctx.doc.new_merge_key())
        return True

    def drag_move(self, p, ev):
        if not self.drag:
            return
        hit, key = self.drag
        what, kid = hit[0], hit[1]
        if what in ("curve", "zone", "pivot"):
            r = self.ctx.snap(p)
            self.ctx.layer.show_snap(r)
            self.ctx.doc.edit("Move point", lambda t: move_item_point(t, hit, r.point), key)
            return
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
        item = self.ctx.doc.selected_item
        if item is not None and item[0] in ("curve", "zone", "pivot") and (item[2] is not None or item[0] == "pivot"):
            pos, _ = parse_coords(s, self.ctx.unit)
            self.ctx.doc.edit("Move point", lambda t: move_item_point(t, item, pos))
            return True
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


def move_item_point(t, hit, pos):
    """Move a curve control point, zone corner or fixed pivot."""
    kind, iid, idx = hit
    if kind == "curve":
        c = next(c for c in t.curves if c.id == iid)
        c.points[idx] = pos
    elif kind == "zone":
        z = next(z for z in t.zones if z.id == iid)
        z.polygon[idx] = pos
    elif kind == "pivot":
        next(f for f in t.pivots if f.id == iid).pos = pos


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


class PolylineTool(Tool):
    """Click points one by one. Finish by clicking the first point again
    (closes the shape), double-click, right-click, Enter, or the Finish
    button; Backspace removes the last point; Esc cancels."""

    min_points = 2
    noun = "shape"
    default_closed = True  # finishing with Enter etc. closes shapes of 3+ points
    cursor = QtCore.Qt.CrossCursor

    def __init__(self, ctx):
        super().__init__(ctx)
        self.pts = []

    @property
    def drawing(self):
        return bool(self.pts)

    def _prompt(self):
        n = len(self.pts)
        if not n:
            return self.prompt
        how = "click the first point to close · double-click, right-click or Enter to finish"
        return f"{self.noun.capitalize()}: {n} point{'s' if n != 1 else ''} · {how} · Backspace undoes a point · Esc cancels"

    def _changed(self):
        self.ctx.set_prompt(self._prompt())
        self.ctx.w.update_drawing_actions()
        if self.pts:
            self.ctx.layer.show_preview(line=self.pts, points=self.pts)
        else:
            self.ctx.layer.clear_feedback()

    def activate(self):
        super().activate()
        self._changed()

    def deactivate(self):
        self.pts = []
        super().deactivate()
        self.ctx.w.update_drawing_actions()

    def _ref(self):
        return self.pts[-1] if self.pts else None

    def _near_first(self, p):
        return len(self.pts) >= 3 and abs(p - self.pts[0]) <= SNAP_PX * self.ctx.layer.mm_per_px()

    def hover(self, p):
        if self._near_first(p):
            self.ctx.layer.show_snap(SnapResult(self.pts[0], "object", label="close"))
            self.ctx.layer.show_preview(line=self.pts + [self.pts[0]], points=self.pts)
            return
        r = self.ctx.snap(p, ref=self._ref())
        self.ctx.layer.show_snap(r)
        if self.pts:
            self.ctx.layer.show_preview(line=self.pts + [r.point], points=self.pts)

    def click(self, p, ev):
        if ev is not None and ev.double():
            self.finish()
            return True
        if self._near_first(p):
            self.finish(closed=True)
            return True
        self.pts.append(self.ctx.snap(p, ref=self._ref()).point)
        self._changed()
        return True

    def right_click(self, p, ev):
        if self.pts:
            self.finish()
            return True
        return False

    def key(self, key):
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.finish()
        elif key == QtCore.Qt.Key_Escape and self.pts:
            self.cancel()
        elif key == QtCore.Qt.Key_Backspace and self.pts:
            self.pts.pop()
            self._changed()
        else:
            return False
        return True

    def text(self, s):
        last = (self.pts[-1], 0.0) if self.pts else None
        pos, _ = parse_coords(s, self.ctx.unit, last)
        self.pts.append(pos)
        self._changed()
        return True

    def cancel(self):
        self.pts = []
        self._changed()

    def finish(self, closed=None):
        pts = list(self.pts)
        # Drop a duplicate final point (from the double-click's first click).
        if len(pts) >= 2 and abs(pts[-1] - pts[-2]) < 1e-9:
            pts.pop()
        self.pts = []
        self._changed()
        if len(pts) < self.min_points:
            self.ctx.w.statusBar().showMessage(f"A {self.noun} needs at least {self.min_points} points", 3000)
            return
        if closed is None:
            closed = self.default_closed and len(pts) >= 3
        self.commit(pts, closed)

    def commit(self, pts, closed):
        raise NotImplementedError


class BodyTool(PolylineTool):
    name = "body"
    noun = "body outline"
    prompt = "Body: click around the outline of the moving part · finish with Enter, right-click, double-click or by clicking the first point"

    def commit(self, pts, closed):
        def fn(t):
            if t.keyframes:
                ref = t.keyframes[0]
            else:
                c = complex(np.mean(pts))
                ref = Keyframe(pos=c, angle=0.0)
                t.keyframes.append(ref)
            t.body = Body([list(pose_inverse(pts, ref.pos, ref.angle))], closed=closed)
        self.ctx.doc.edit("Set body outline", fn)


class CurveTool(PolylineTool):
    """Click spline points, or press-drag to sketch freehand (smoothed into a
    few editable points). A curve closes if you finish on its first point."""

    name = "curve"
    noun = "curve"
    default_closed = False
    prompt = ("Curve: drag to sketch freehand, or click points · finish with Enter, right-click or double-click · "
              "click the first point to close it")

    def __init__(self, ctx):
        super().__init__(ctx)
        self.stroke = None

    def drag_start(self, p, ev):
        if self.pts:
            return False  # already clicking points: let the view pan
        self.stroke = [self.ctx.snap(p).point]
        return True

    def drag_move(self, p, ev):
        self.stroke.append(p)
        self.ctx.layer.show_preview(line=self.stroke)

    def drag_end(self, p, ev):
        stroke, self.stroke = self.stroke + [p], None
        self.ctx.layer.clear_feedback()
        mpp = self.ctx.layer.mm_per_px()
        if len(stroke) < 3 or sum(abs(b - a) for a, b in zip(stroke, stroke[1:])) < 20 * mpp:
            return
        closed = abs(stroke[-1] - stroke[0]) < 15 * mpp
        pts = list(simplify(resample_even(stroke, 200), 3 * mpp))
        if closed and len(pts) > 3:
            pts = pts[:-1]
        self.commit(pts, closed and len(pts) >= 3)

    def commit(self, pts, closed):
        c = Curve(points=list(pts), closed=closed)
        self.ctx.doc.edit("Add curve", lambda t: t.curves.append(c))
        self.ctx.doc.select_item(("curve", c.id, None))
        if self.ctx.doc.target.mode != "path":
            self.ctx.doc.edit("Change synthesis mode", lambda t: setattr(t, "mode", "path"))


class ZoneTool(PolylineTool):
    name = "zone"
    noun = "pivot zone"
    min_points = 3
    prompt = ("Zone: click the corners of a region where ground pivots are allowed (hold Ctrl on the last click "
              "for a keep-out zone) · finish with Enter, right-click, double-click or the first point")

    def commit(self, pts, closed):
        allow = not (self.ctx.modifiers() & QtCore.Qt.ControlModifier)
        z = Zone(polygon=list(pts), allow=allow)
        self.ctx.doc.edit("Add pivot zone" if allow else "Add keep-out zone", lambda t: t.zones.append(z))
        self.ctx.doc.select_item(("zone", z.id, None))


class PivotTool(Tool):
    name = "pivot"
    prompt = ("Fixed pivot: click where a ground pivot must be · press-drag to fix a slider axis instead "
              "(Shift: 15° steps) · or type x, y")
    cursor = QtCore.Qt.CrossCursor

    def __init__(self, ctx):
        super().__init__(ctx)
        self.anchor = None

    def _commit(self, pos, slider_angle=None):
        fp = FixedPivot(pos=pos, slider_angle=slider_angle)
        self.ctx.doc.edit("Add fixed slider axis" if slider_angle is not None else "Add fixed pivot",
                          lambda t: t.pivots.append(fp))
        self.ctx.doc.select_item(("pivot", fp.id, None))

    def click(self, p, ev):
        self._commit(self.ctx.snap(p).point)
        return True

    def drag_start(self, p, ev):
        self.anchor = self.ctx.snap(p).point
        return True

    def drag_move(self, p, ev):
        ang = self.ctx.snap_angle(cmath.phase(p - self.anchor)) if p != self.anchor else 0.0
        tip = self.anchor + abs(p - self.anchor) * cmath.exp(1j * ang)
        self.ctx.layer.show_preview(line=[2 * self.anchor - tip, tip], points=[self.anchor])

    def drag_end(self, p, ev):
        self.ctx.layer.clear_feedback()
        if abs(p - self.anchor) < DRAG_ANGLE_MIN_PX * self.ctx.layer.mm_per_px():
            self._commit(self.anchor)
        else:
            self._commit(self.anchor, self.ctx.snap_angle(cmath.phase(p - self.anchor)) % math.pi)

    def text(self, s):
        pos, _ = parse_coords(s, self.ctx.unit)
        self._commit(pos)
        return True


class MeasureTool(Tool):
    name = "measure"
    prompt = "Measure: click two points to see the distance and angle between them (snapping applies)"
    cursor = QtCore.Qt.CrossCursor

    def __init__(self, ctx):
        super().__init__(ctx)
        self.a = None
        self.b = None

    def deactivate(self):
        self.a = self.b = None
        self.ctx.layer.show_measure(None)
        super().deactivate()

    def _show(self, a, b):
        from kinsyn.core.units import format_angle, format_length
        d = abs(b - a)
        ang = cmath.phase(b - a) if d else 0.0
        u = self.ctx.unit
        txt = (f"{format_length(d, u)} {u}  ∠{format_angle(ang, 1)}°  "
               f"(Δx {format_length((b - a).real, u)}, Δy {format_length((b - a).imag, u)})")
        self.ctx.layer.show_measure((a, b), txt)
        self.ctx.set_prompt(f"Measure: {txt}")

    def hover(self, p):
        r = self.ctx.snap(p, ref=self.a if self.b is None else None)
        self.ctx.layer.show_snap(r)
        if self.a is not None and self.b is None:
            self._show(self.a, r.point)

    def click(self, p, ev):
        q = self.ctx.snap(p, ref=self.a if self.b is None else None).point
        if self.a is None or self.b is not None:
            self.a, self.b = q, None
            self.ctx.layer.show_measure(None)
        else:
            self.b = q
            self._show(self.a, self.b)
        return True
