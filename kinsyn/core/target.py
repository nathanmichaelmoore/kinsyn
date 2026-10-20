"""The synthesis target: an ordered list of keyframes (poses or points) plus
optional body outline, curves, pivot zones and fixed pivots.

Everything is in mm / radians. The target is plain data; the GUI edits it by
replacing whole copies (which makes undo trivial)."""

import copy
import math
import uuid
from dataclasses import dataclass, field

import numpy as np

TIMING_MODES = ("free", "absolute", "relative")
MODES = ("motion", "path")


def new_id():
    return uuid.uuid4().hex[:8]


def _c(v):
    return [v.real, v.imag]


def _z(v):
    return complex(v[0], v[1])


@dataclass
class Keyframe:
    pos: complex
    angle: float = 0.0  # orientation of the moving body (motion generation)
    timing: str = "free"  # free | absolute (input value t) | relative (t after previous)
    t: float = 0.0
    tol: float = 0.0  # position tolerance, mm (0 = exact precision point)
    tol_angle: float = 0.0  # orientation tolerance, rad
    weight: float = 1.0
    id: str = field(default_factory=new_id)

    @property
    def exact(self):
        return self.tol == 0 and self.tol_angle == 0

    def to_dict(self):
        return {"id": self.id, "pos": _c(self.pos), "angle": self.angle, "timing": self.timing,
                "t": self.t, "tol": self.tol, "tol_angle": self.tol_angle, "weight": self.weight}

    @staticmethod
    def from_dict(d):
        return Keyframe(pos=_z(d["pos"]), angle=d.get("angle", 0.0), timing=d.get("timing", "free"),
                        t=d.get("t", 0.0), tol=d.get("tol", 0.0), tol_angle=d.get("tol_angle", 0.0),
                        weight=d.get("weight", 1.0), id=d.get("id") or new_id())


def pose_transform(points, pos, angle):
    """Map body-frame points into the world at a pose."""
    return pos + np.asarray(points, complex) * np.exp(1j * angle)


def pose_inverse(points, pos, angle):
    """Map world points into the body frame of a pose."""
    return (np.asarray(points, complex) - pos) * np.exp(-1j * angle)


@dataclass
class Body:
    """Outline of the part being moved, in its own frame (origin = the
    keyframe reference point, x-axis = keyframe angle 0)."""
    polylines: list  # list of lists of complex
    closed: bool = True

    def at(self, pos, angle):
        return [pose_transform(p, pos, angle) for p in self.polylines]

    def to_dict(self):
        return {"polylines": [[_c(z) for z in pl] for pl in self.polylines], "closed": self.closed}

    @staticmethod
    def from_dict(d):
        return Body([[_z(p) for p in pl] for pl in d["polylines"]], d.get("closed", True))


def catmull_rom(points, closed, per_segment=24):
    """Centripetal-free (uniform) Catmull-Rom spline through the points."""
    P = np.asarray(points, complex)
    n = len(P)
    if n < 2:
        return P.copy()
    if closed:
        ext = np.concatenate([P[-1:], P, P[:2]])
        segs = n
    else:
        ext = np.concatenate([2 * P[:1] - P[1:2], P, 2 * P[-1:] - P[-2:-1]])
        segs = n - 1
    t = np.linspace(0, 1, per_segment, endpoint=False)
    t2, t3 = t * t, t * t * t
    out = []
    for i in range(segs):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense = np.concatenate(out)
    return np.append(dense, P[0] if closed else P[-1])


def resample_even(poly, n, closed=False):
    """n points evenly spaced by arc length along a polyline."""
    poly = np.asarray(poly, complex)
    if closed:
        poly = np.append(poly, poly[0])
    seg = np.abs(np.diff(poly))
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if s[-1] == 0:
        return np.repeat(poly[:1], n)
    targets = np.linspace(0, s[-1], n, endpoint=not closed)
    return np.interp(targets, s, poly.real) + 1j * np.interp(targets, s, poly.imag)


@dataclass
class Curve:
    points: list  # spline control points (the spline passes through them)
    closed: bool = False
    id: str = field(default_factory=new_id)

    def dense(self, per_segment=24):
        return catmull_rom(self.points, self.closed, per_segment)

    def sample(self, n):
        return resample_even(self.dense(), n, self.closed)

    def to_dict(self):
        return {"id": self.id, "points": [_c(p) for p in self.points], "closed": self.closed}

    @staticmethod
    def from_dict(d):
        return Curve([_z(p) for p in d["points"]], d.get("closed", False), d.get("id") or new_id())


@dataclass
class Zone:
    polygon: list
    allow: bool = True  # allowed region for ground pivots, else keep-out
    id: str = field(default_factory=new_id)

    def to_dict(self):
        return {"id": self.id, "polygon": [_c(p) for p in self.polygon], "allow": self.allow}

    @staticmethod
    def from_dict(d):
        return Zone([_z(p) for p in d["polygon"]], d.get("allow", True), d.get("id") or new_id())


@dataclass
class FixedPivot:
    pos: complex
    slider_angle: float | None = None  # set for a fixed slider axis instead of a pin
    id: str = field(default_factory=new_id)

    def to_dict(self):
        return {"id": self.id, "pos": _c(self.pos), "slider_angle": self.slider_angle}

    @staticmethod
    def from_dict(d):
        return FixedPivot(_z(d["pos"]), d.get("slider_angle"), d.get("id") or new_id())


@dataclass
class Target:
    mode: str = "motion"
    keyframes: list = field(default_factory=list)
    body: Body | None = None
    curves: list = field(default_factory=list)
    zones: list = field(default_factory=list)
    pivots: list = field(default_factory=list)

    def copy(self):
        return copy.deepcopy(self)

    def index_of(self, kid):
        for i, k in enumerate(self.keyframes):
            if k.id == kid:
                return i
        return None

    def keyframe(self, kid):
        i = self.index_of(kid)
        return None if i is None else self.keyframes[i]

    def scale(self):
        pts = [k.pos for k in self.keyframes] + [p for c in self.curves for p in c.points]
        if len(pts) < 2:
            return 100.0
        z = np.array(pts)
        return max(float(np.ptp(z.real)), float(np.ptp(z.imag)), 1.0)

    # --- solver guidance -------------------------------------------------
    def solver_hint(self):
        n = len(self.keyframes)
        noun = "pose" if self.mode == "motion" else "point"
        if n == 0 and not self.curves:
            return f"Place {noun}s to define the motion"
        if self.mode == "path":
            total = n + sum(1 for _ in self.curves)
            if self.curves:
                return f"{n} point(s) + {len(self.curves)} curve(s) → path optimizer"
            return f"{total} {noun}(s) → path optimizer" if total else ""
        exact = all(k.exact for k in self.keyframes)
        timed = sum(k.timing != "free" for k in self.keyframes[1:])
        if n < 2:
            return "Add at least 2 poses"
        if not exact:
            return f"{n} poses with tolerance → optimizer"
        if timed and n > 3:
            return f"{n} exact poses with prescribed timing → optimizer (exact solutions only up to 3 timed poses)"
        return {
            2: "2 exact poses → closed-form dyads (many free choices)",
            3: "3 exact poses → dyad solve (choose the free parameters)",
            4: "4 exact poses → Burmester curves (pick pivots on the curves)",
            5: "5 exact poses → Burmester points (finite solution set)",
        }.get(n, f"{n} exact poses → optimizer (more than 5 is over-constrained for a four-bar)")

    def warnings(self):
        """List of (keyframe index or None, message)."""
        out = []
        tol = 1e-3 * self.scale()
        ks = self.keyframes
        for i in range(len(ks)):
            for j in range(i + 1, len(ks)):
                same_ang = self.mode == "path" or abs(_wrap(ks[i].angle - ks[j].angle)) < math.radians(0.5)
                if abs(ks[i].pos - ks[j].pos) < tol and same_ang:
                    out.append((j, f"{'Poses' if self.mode == 'motion' else 'Points'} {i + 1} and {j + 1} "
                                   "are nearly identical → poorly conditioned"))
        abs_t = [(i, k.t) for i, k in enumerate(ks) if k.timing == "absolute"]
        for (i, a), (j, b) in zip(abs_t, abs_t[1:]):
            if b <= a:
                out.append((j, f"Keyframe {j + 1} is timed before keyframe {i + 1}"))
        if ks and ks[0].timing == "relative":
            out.append((0, "The first keyframe cannot be timed relative to a previous one"))
        return out

    # --- serialisation ---------------------------------------------------
    def to_dict(self):
        return {"mode": self.mode, "keyframes": [k.to_dict() for k in self.keyframes],
                "body": self.body.to_dict() if self.body else None,
                "curves": [c.to_dict() for c in self.curves], "zones": [z.to_dict() for z in self.zones],
                "pivots": [p.to_dict() for p in self.pivots]}

    @staticmethod
    def from_dict(d):
        return Target(mode=d.get("mode", "motion"),
                      keyframes=[Keyframe.from_dict(k) for k in d.get("keyframes", [])],
                      body=Body.from_dict(d["body"]) if d.get("body") else None,
                      curves=[Curve.from_dict(c) for c in d.get("curves", [])],
                      zones=[Zone.from_dict(z) for z in d.get("zones", [])],
                      pivots=[FixedPivot.from_dict(p) for p in d.get("pivots", [])])


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


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def simplify(points, tol):
    """Ramer-Douglas-Peucker: the fewest points that keep the polyline
    within `tol` of the original. Used to turn a freehand stroke into a few
    editable spline control points."""
    P = np.asarray(points, complex)
    if len(P) < 3:
        return P.copy()
    keep = np.zeros(len(P), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(P) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = P[i], P[j]
        seg = b - a
        mid = P[i + 1:j]
        if abs(seg) < 1e-12:
            d = np.abs(mid - a)
        else:
            d = np.abs(((mid - a) * np.conj(seg)).imag) / abs(seg)
        k = int(np.argmax(d))
        if d[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return P[keep]


def point_in_polygon(p, polygon):
    """Even-odd rule test for a point inside a polygon (list of complex)."""
    inside = False
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if (a.imag > p.imag) != (b.imag > p.imag):
            x = a.real + (p.imag - a.imag) * (b.real - a.real) / (b.imag - a.imag)
            if p.real < x:
                inside = not inside
    return inside
