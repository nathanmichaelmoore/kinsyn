"""Snapping: object points, angle increments, alignment guides and grid.
Pure geometry (mm); the GUI supplies the tolerance in mm for its zoom level."""

import math
from dataclasses import dataclass, field

import numpy as np

INCH = 25.4


@dataclass
class SnapResult:
    point: complex
    kind: str | None = None  # "object" | "angle" | "align" | "grid" | None
    guides: list = field(default_factory=list)  # (a, b) segments to draw
    label: str = ""


def nice_step(approx_mm, unit):
    """A grid step near `approx_mm`: 1-2-5 series in metric units, binary
    fractions / multiples of an inch in inches."""
    if approx_mm <= 0:
        return 1.0
    if unit == "in":
        k = round(math.log2(approx_mm / INCH))
        return INCH * 2.0 ** max(-6, k)
    exp = math.floor(math.log10(approx_mm))
    base = approx_mm / 10 ** exp
    m = min((1, 2, 5, 10), key=lambda c: abs(math.log(base / c)))
    return m * 10 ** exp


def snap_point(p, *, tol, points=(), grid_step=None, ref=None, angle_step=None,
               objects=True, align=True):
    """Snap raw point `p` (complex, mm).

    Priority: object points within `tol` > angle constraint from `ref` (when
    `angle_step` is given) > alignment with existing points (per axis) > grid."""
    pts = np.asarray(list(points), complex)
    if objects and len(pts):
        d = np.abs(pts - p)
        i = int(np.argmin(d))
        if d[i] <= tol:
            return SnapResult(complex(pts[i]), "object", label="point")

    if ref is not None and angle_step:
        v = p - ref
        r = abs(v)
        if r > 0:
            ang = round(math.atan2(v.imag, v.real) / angle_step) * angle_step
            u = complex(math.cos(ang), math.sin(ang))
            if grid_step:
                r = max(grid_step, round(r / grid_step) * grid_step)
            q = ref + r * u
            return SnapResult(q, "angle", [(ref, ref + 1.5 * r * u)], f"{math.degrees(ang):.0f}°")

    x, y = p.real, p.imag
    kind, guides = None, []
    ax = ay = False
    if align and len(pts):
        dx = np.abs(pts.real - x)
        i = int(np.argmin(dx))
        if dx[i] <= tol:
            x, ax = float(pts[i].real), True
            guides.append((complex(x, pts[i].imag), None))
        dy = np.abs(pts.imag - y)
        j = int(np.argmin(dy))
        if dy[j] <= tol:
            y, ay = float(pts[j].imag), True
            guides.append((complex(pts[j].real, y), None))
        if ax or ay:
            kind = "align"
    if grid_step:
        if not ax:
            x = round(x / grid_step) * grid_step
        if not ay:
            y = round(y / grid_step) * grid_step
        kind = kind or "grid"
    q = complex(x, y)
    # Alignment guides run from the aligned point to the snapped point.
    guides = [(a, q) for a, _ in guides]
    return SnapResult(q, kind, guides, "aligned" if kind == "align" else "")
