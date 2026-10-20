"""Burmester theory: motion generation for 4 and 5 poses.

With 4 poses, a ground pivot G works for a pin-pin dyad only if the three
equations for its moving pivot (dyad.rr_system) agree, i.e. the 3x3
determinant [A | b] vanishes. Every entry is affine in G, so that is a cubic
curve: the **center-point curve**. Each of its points has one moving pivot;
those form the **circle-point curve**. With 5 poses, the curves of poses
1-2-3-4 and 1-2-3-5 must both pass through G: their real intersections that
also fit pose 5 are the **Burmester points** (0, 2 or 4 of them).

Slider dyads are the limit of a pivot at infinity: a rail direction (or a
slide direction, for a swivel) works only at the roots of the matching
determinant. Those are the slider options.

Everything here is plain NumPy (no GUI)."""

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import brentq

from .dyad import Poses, pr_from_direction, pr_system, rp_from_direction, rp_system, rr_from_ground, rr_system


def _sub(poses: Poses, idx):
    return Poses(poses.P[list(idx)], poses.th[list(idx)])


def _det(A, b):
    return np.linalg.det(np.concatenate([A[..., :3, :], b[..., :3, None]], -1))


def center_point_fn(poses: Poses, G):
    """The cubic whose zero set is the center-point curve of the first four
    poses. Vectorised over G."""
    return _det(*rr_system(_sub(poses, range(4)), G))


# --------------------------------------------------------------------------
# Contouring (marching squares) on a grid

def _contour(fn, box, n):
    """Zero set of fn (vectorised over complex points) in box = (x0, x1, y0,
    y1), as a list of polylines (complex arrays)."""
    x0, x1, y0, y1 = box
    xs, ys = np.linspace(x0, x1, n), np.linspace(y0, y1, n)
    Z = xs[None, :] + 1j * ys[:, None]
    F = fn(Z)
    S = F > 0

    def point(edge):
        kind, i, j = edge
        za, fa = Z[i, j], F[i, j]
        zb, fb = (Z[i, j + 1], F[i, j + 1]) if kind == "h" else (Z[i + 1, j], F[i + 1, j])
        t = fa / (fa - fb) if fa != fb else 0.5
        return za + t * (zb - za)

    links = {}

    def link(e1, e2):
        links.setdefault(e1, []).append(e2)
        links.setdefault(e2, []).append(e1)

    cells = np.argwhere((S[:-1, :-1] != S[:-1, 1:]) | (S[:-1, :-1] != S[1:, :-1]) | (S[1:, 1:] != S[:-1, 1:])
                        | (S[1:, 1:] != S[1:, :-1]))
    for i, j in cells:
        # Crossed edges in order round the cell: bottom, right, top, left.
        edges = [("h", i, j), ("v", i, j + 1), ("h", i + 1, j), ("v", i, j)]
        ends = [((i, j), (i, j + 1)), ((i, j + 1), (i + 1, j + 1)), ((i + 1, j), (i + 1, j + 1)),
                ((i, j), (i + 1, j))]
        crossed = [e for e, (a, b) in zip(edges, ends) if S[a] != S[b]]
        if len(crossed) == 2:
            link(*crossed)
        elif len(crossed) == 4:
            # Saddle: decide the pairing by the sign at the cell centre.
            centre = fn(np.array([(Z[i, j] + Z[i + 1, j + 1]) / 2]))[0] > 0
            if centre == S[i, j]:
                link(crossed[0], crossed[1])
                link(crossed[2], crossed[3])
            else:
                link(crossed[0], crossed[3])
                link(crossed[1], crossed[2])

    seen = set()
    lines = []
    # Open chains (ending at the box edge) first, then closed loops.
    starts = [e for e, nb in links.items() if len(nb) == 1] + list(links)
    for start in starts:
        if start in seen:
            continue
        chain = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxt = [e for e in links[cur] if e != prev and e not in seen]
            if not nxt:
                if len(links[cur]) == 2 and start in links[cur] and len(chain) > 2:
                    chain.append(start)  # closed loop
                break
            prev, cur = cur, nxt[0]
            chain.append(cur)
            seen.add(cur)
        if len(chain) >= 2:
            lines.append(np.array([point(e) for e in chain]))
    return lines


def _newton(fn, z, scale, steps=2):
    """A few vectorised Newton steps of z towards fn(z) = 0, along the
    gradient."""
    h = 1e-6 * scale
    for _ in range(steps):
        f = fn(z)
        g = (fn(z + h) - fn(z - h)) / (2 * h) + 1j * (fn(z + 1j * h) - fn(z - 1j * h)) / (2 * h)
        with np.errstate(invalid="ignore", divide="ignore"):
            step = np.where(np.abs(g) > 0, f * g / np.abs(g) ** 2, 0)
        z = z - np.nan_to_num(step)
    return z


def project_to_curve(poses: Poses, G, max_move=None):
    """Nearest-ish point of the center-point curve (first four poses) to G,
    by Newton steps along the gradient. None if it does not converge within
    `max_move` of G."""
    scale = poses.scale()
    fn = lambda z: center_point_fn(poses, z)
    z = complex(G)
    for _ in range(50):
        z_new = complex(_newton(fn, np.array([z]), scale, 1)[0])
        if abs(z_new - z) < 1e-12 * scale:
            z = z_new
            break
        z = z_new
    if not np.isfinite(z) or (max_move is not None and abs(z - G) > max_move):
        return None
    return z


# --------------------------------------------------------------------------
# Results

@dataclass
class Curves:
    """Center-point and circle-point curves of 4 poses, inside a box."""
    center: list = field(default_factory=list)  # polylines of ground pivots
    circle: list = field(default_factory=list)  # matching moving pivots (world, pose 1)
    box: tuple = ()


def default_box(poses: Poses, zones=(), pad=1.2):
    pts = list(poses.P) + [p for z in zones if z.allow for p in z.polygon]
    z = np.array(pts)
    s = max(float(np.ptp(z.real)), float(np.ptp(z.imag)), poses.scale())
    cx, cy = (z.real.min() + z.real.max()) / 2, (z.imag.min() + z.imag.max()) / 2
    h = s / 2 + pad * s
    return cx - h, cx + h, cy - h, cy + h


def curves(poses: Poses, box=None, n=220):
    """Center-point curve (and circle points) of the first four poses."""
    box = box or default_box(poses)
    scale = poses.scale()
    fn = lambda z: center_point_fn(poses, z)
    out = Curves(box=box)
    for line in _contour(fn, box, n):
        line = _newton(fn, line, scale)
        A, b = rr_system(_sub(poses, range(4)), line)
        circ = np.full(len(line), np.nan + 0j)
        for k in range(len(line)):
            m, *_ = np.linalg.lstsq(A[k], b[k], rcond=None)
            circ[k] = poses.P[0] + complex(*m) * poses.a[0]
        # Circle points can run off to infinity near special points: split there.
        far = np.abs(circ - np.mean(poses.P)) > 20 * scale
        circ[far] = np.nan
        out.center.append(line)
        out.circle.append(circ)
    return out


def sample_curve(c: Curves, n):
    """About n points spread evenly (by length) over the center-point curve."""
    lengths = [float(np.abs(np.diff(l)).sum()) for l in c.center]
    total = sum(lengths)
    if total == 0:
        return []
    pts = []
    for line, L in zip(c.center, lengths):
        k = max(1, round(n * L / total))
        s = np.concatenate([[0], np.cumsum(np.abs(np.diff(line)))])
        t = (np.arange(k) + 0.5) / k * L
        pts += list(np.interp(t, s, line.real) + 1j * np.interp(t, s, line.imag))
    return pts


def burmester_points(poses: Poses, box=None, n=260):
    """Ground pivots that work for all 5 poses (with their dyads)."""
    scale = poses.scale()
    pa, pb = _sub(poses, (0, 1, 2, 3)), _sub(poses, (0, 1, 2, 4))
    fa = lambda z: center_point_fn(pa, z)
    fb = lambda z: center_point_fn(pb, z)
    box = box or default_box(poses, pad=2.5)
    found = []
    for line in _contour(fa, box, n):
        vb = fb(line)
        for k in np.nonzero(np.sign(vb[:-1]) * np.sign(vb[1:]) < 0)[0]:
            t = vb[k] / (vb[k] - vb[k + 1])
            z = line[k] + t * (line[k + 1] - line[k])
            z = _newton2(fa, fb, z, scale)
            if z is None:
                continue
            d = rr_from_ground(poses, z)
            if d is None or abs(poses.world(d.m)[0] - z) < 1e-3 * scale:
                continue  # not a real solution, or a zero-length crank (a pole)
            if all(abs(z - q.G) > 1e-6 * scale for q in found):
                found.append(d)
    return found


def _newton2(fa, fb, z, scale, iters=40):
    """Solve fa(z) = fb(z) = 0 (two real equations in x, y)."""
    h = 1e-6 * scale
    for _ in range(iters):
        F = np.array([fa(np.array([z]))[0], fb(np.array([z]))[0]])
        J = np.empty((2, 2))
        for col, dz in enumerate((h, 1j * h)):
            J[:, col] = (np.array([fa(np.array([z + dz]))[0], fb(np.array([z + dz]))[0]]) - F) / h
        try:
            dx, dy = np.linalg.solve(J, -F)
        except np.linalg.LinAlgError:
            return None
        z += complex(dx, dy)
        if abs(complex(dx, dy)) < 1e-12 * scale:
            return z
    return z if np.isfinite(z) else None


def slider_directions(poses: Poses, kind, n=720):
    """Rail directions (kind "PR") or body slide directions ("RP") that
    work for all the poses (4 or 5). Angles in [0, pi)."""
    system = pr_system if kind == "PR" else rp_system
    four = _sub(poses, range(4))
    g = lambda t: _det(*system(four, t))
    # Start at an odd angle so a root at a "round" direction (0, 90 deg) is
    # never exactly on a sample, where its sign would be numerical noise.
    ts = 0.0123456 + np.linspace(0, math.pi, n + 1)
    vals = g(ts)
    roots = []
    for k in np.nonzero(np.sign(vals[:-1]) * np.sign(vals[1:]) <= 0)[0]:
        if vals[k] == 0:
            r = ts[k]
        else:
            r = brentq(lambda t: float(g(np.array([t]))[0]), ts[k], ts[k + 1], xtol=1e-14)
        r = r % math.pi
        if all(min(abs(r - q), math.pi - abs(r - q)) > 1e-9 for q in roots):
            roots.append(r)
    if len(poses) > 4:
        # Roots of the first four poses that also fit the rest.
        fn = pr_from_direction if kind == "PR" else rp_from_direction
        roots = [r for r in roots if fn(poses, r) is not None]
    return roots


_last_points = (None, [])


def _cached_points(poses: Poses):
    """Burmester points of these poses, remembered for the last set of poses
    (both dyads of a design ask for the same ones). The GUI thread and the
    background search both use it, so the pair is read and replaced whole."""
    global _last_points
    key = poses.P.tobytes() + poses.th.tobytes()
    cached_key, pts = _last_points
    if cached_key != key:
        pts = [d.G for d in burmester_points(poses)]
        _last_points = (key, pts)
    return pts


def snap_ground(poses: Poses, G, scale_frac=0.08):
    """Move a chosen ground pivot onto what works for 4 or 5 poses: the
    center-point curve, or the nearest Burmester point. None if nothing is
    within `scale_frac` of the target size (5 poses)."""
    if len(poses) <= 3:
        return G
    if len(poses) == 4:
        return project_to_curve(poses, G, max_move=0.5 * poses.scale())
    pts = _cached_points(poses)
    if not pts:
        return None
    best = min(pts, key=lambda z: abs(z - G))
    return best if abs(best - G) <= scale_frac * poses.scale() else None


def snap_direction(poses: Poses, kind, angle, tol=math.radians(10)):
    """Nearest working rail ("PR") or slide ("RP") direction for 4 or 5
    poses, if one is within `tol` (angles are modulo pi)."""
    if len(poses) <= 3:
        return angle
    roots = slider_directions(poses, kind)
    if not roots:
        return None
    gap = lambda r: abs((r - angle + math.pi / 2) % math.pi - math.pi / 2)
    best = min(roots, key=gap)
    return best if gap(best) <= tol else None
