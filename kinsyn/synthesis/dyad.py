"""Dyads for motion generation.

A dyad is the two-joint chain that connects a moving body to the ground.
Three kinds cover the single-loop pin and slider mechanisms:

- RR: a ground pin G and a pin on the body (moving pivot, body coords m).
- PR: a slider block on a straight ground rail, pinned to the body at m.
  The rail direction is `angle` (world).
- RP: a ground pin G (swivel) that the body slides through. The slide line
  has direction `angle` in the body frame.

Each kind has one "primary" free choice: G for RR, the rail direction for
PR, and the slide direction for RP. Once it is chosen, the other unknown
(m for RR and PR, G for RP) follows from a linear system with one row per
pose after the first. Three poses give a unique dyad, and two poses leave a
line of solutions (sampled by the caller with an offset `s` along it).

Body coordinates are relative to the pose: origin at the keyframe point,
x-axis along the keyframe angle.
"""

import math
from dataclasses import dataclass, replace

import numpy as np

DEGENERATE = 1e-9


@dataclass(frozen=True)
class Poses:
    P: np.ndarray  # complex, keyframe points
    th: np.ndarray  # keyframe angles (rad)

    @staticmethod
    def of(keyframes):
        return Poses(np.array([k.pos for k in keyframes], complex),
                     np.array([k.angle for k in keyframes], float))

    def __len__(self):
        return len(self.P)

    @property
    def a(self):
        return np.exp(1j * self.th)

    def world(self, m):
        """World positions of body point m at every pose."""
        return self.P + m * self.a

    def body(self, z):
        """Body coordinates of world point z at every pose."""
        return (z - self.P) / self.a

    def scale(self):
        if len(self) < 2:
            return 100.0
        return max(float(np.ptp(self.P.real)), float(np.ptp(self.P.imag)), 1.0)


@dataclass(frozen=True)
class Dyad:
    kind: str  # "RR" | "PR" | "RP"
    G: complex | None = None  # ground pin (RR, RP)
    m: complex | None = None  # moving pin, body coords (RR, PR)
    angle: float | None = None  # PR: rail direction (world); RP: slide direction (body)
    # The free choices that produced it, so it can be re-solved when the poses move.
    source: tuple = ()

    def describe(self):
        return {"RR": "pin-pin", "PR": "slider on ground", "RP": "swivel"}[self.kind]


# --------------------------------------------------------------------------
# The linear systems. Each takes the free choice (possibly an array of them)
# and returns A (..., n-1, 2) and b (..., n-1) for the unknown (x, y), one
# row per pose after the first. With 4+ poses there are more rows than
# unknowns, and a dyad exists only where the system is consistent: that is
# what the Burmester curves are.

def _re_rows(c):
    """Rows for Re[c z] as linear forms in (z.real, z.imag)."""
    return np.stack([c.real, -c.imag], -1)


def _im_rows(c):
    """Rows for Im[c z]."""
    return np.stack([c.imag, c.real], -1)


def rr_system(poses: Poses, G):
    """Moving pivot m for ground pivot G: |M_j - G| equal for all poses.
    The |m|^2 terms cancel, so each row is linear in m (and affine in G)."""
    u = poses.P - np.asarray(G, complex)[..., None]
    a = poses.a
    c = 2 * (np.conj(u[..., 1:]) * a[1:] - np.conj(u[..., :1]) * a[0])
    b = np.abs(u[..., :1]) ** 2 - np.abs(u[..., 1:]) ** 2
    return _re_rows(c), b


def pr_system(poses: Poses, gamma):
    """Moving pivot m whose positions lie on one line of direction gamma."""
    w = np.exp(-1j * np.asarray(gamma, float))[..., None]
    a = poses.a
    return _im_rows((a[1:] - a[0]) * w), -((poses.P[1:] - poses.P[0]) * w).imag


def rp_system(poses: Poses, phi):
    """Swivel G at equal distance from every position of a body line with
    direction phi (body frame)."""
    v = np.exp(1j * (np.asarray(phi, float)[..., None] + poses.th))
    cv = np.conj(v)
    b = (poses.P[1:] * cv[..., 1:]).imag - (poses.P[0] * cv[..., :1]).imag
    return _im_rows(cv[..., 1:] - cv[..., :1]), b


def _solve_linear(A, b, ref, s=0.0, scale=1.0):
    """Solve A @ (x, y) = b for a complex z.

    Two or more rows: the (least-squares) solution; the caller checks that
    it really fits when there are more rows than unknowns. One row (two
    poses): the point on the solution line nearest `ref`, moved by `s` along
    the line. Returns None when the system is degenerate."""
    A = np.asarray(A, float).reshape(-1, 2)
    b = np.asarray(b, float)
    if len(A) >= 2:
        sv = np.linalg.svd(A, compute_uv=False)
        if sv[-1] < DEGENERATE * max(1.0, sv[0]):
            return None
        x, y = np.linalg.lstsq(A, b, rcond=None)[0]
        return complex(x, y)
    r = A[0]
    nr = float(r @ r)
    if nr < DEGENERATE:
        return None
    # Line {z : r . z = b}: nearest point to ref, then slide along it.
    zr = np.array([ref.real, ref.imag])
    p = zr + (b[0] - r @ zr) / nr * r
    d = np.array([-r[1], r[0]]) / math.sqrt(nr)
    p = p + s * scale * d
    return complex(p[0], p[1])


FIT_TOL = 1e-6  # relative to the size of the problem


def _fits(spread, poses, *sizes):
    return spread <= FIT_TOL * max((poses.scale(), *sizes))


def rr_from_ground(poses: Poses, G, s=0.0):
    """RR dyad with ground pin G: the body point that stays at a constant
    distance from G. With 4 or more poses, G must lie on the center-point
    curve (otherwise None)."""
    m = _solve_linear(*rr_system(poses, G), 0j, s, poses.scale())
    if m is None:
        return None
    r = np.abs(poses.world(m) - G)
    if len(poses) > 3 and not _fits(np.ptp(r), poses, r.max()):
        return None
    return Dyad("RR", G=complex(G), m=m, source=("G", complex(G), s))


def rr_from_timing(poses: Poses, betas, G=None):
    """RR input dyad whose crank turns by betas[j] from pose 1 to pose j.

    Three poses: the standard-form dyad equations
        W (e^{i b_j} - 1) + Z (e^{i a_j} - 1) = P_j - P_1
    give W (crank, G -> M1) and Z (M1 -> P1) uniquely. Two poses: G is free
    and the moving pivot is the fixed point of (crank rotation)^-1 o (body
    displacement)."""
    P, th = poses.P, poses.th
    if len(poses) >= 3:
        A = np.array([[np.exp(1j * betas[j]) - 1, np.exp(1j * (th[j] - th[0])) - 1] for j in (1, 2)])
        if abs(np.linalg.det(A)) < DEGENERATE:
            return None
        W, Z = np.linalg.solve(A, P[1:3] - P[0])
        M1 = P[0] - Z
        G = M1 - W
    else:
        eb, ed = np.exp(1j * betas[1]), np.exp(1j * (th[1] - th[0]))
        if abs(ed - eb) < 1e-6:
            return None
        M1 = (G * (1 - eb) - P[1] + P[0] * ed) / (ed - eb)
    m = complex(poses.body(M1)[0])
    return Dyad("RR", G=complex(G), m=m, source=("timed", complex(G) if len(poses) < 3 else None))


def pr_from_direction(poses: Poses, gamma, s=0.0):
    """PR dyad with rail direction gamma: the body point whose positions
    all lie on one line of that direction. With 4 or more poses only a few
    directions work (Ball points); otherwise None."""
    m = _solve_linear(*pr_system(poses, gamma), 0j, s, poses.scale())
    if m is None:
        return None
    M = poses.world(m)
    if len(poses) > 3 and not _fits(np.ptp(((M - M[0]) * np.exp(-1j * gamma)).imag), poses):
        return None
    return Dyad("PR", m=m, angle=float(gamma), source=("gamma", float(gamma), s))


def rp_from_direction(poses: Poses, phi, s=0.0):
    """RP dyad whose body slides along direction phi (body frame) through
    a ground swivel G: G keeps the same distance from the slide line in
    every pose. Linear in G, and independent of where the line sits on the
    body (that only changes the offset). With 4 or more poses only a few
    directions work; otherwise None."""
    G = _solve_linear(*rp_system(poses, phi), complex(np.mean(poses.P)), s, poses.scale())
    if G is None:
        return None
    v = np.exp(1j * (phi + poses.th))
    if len(poses) > 3 and not _fits(np.ptp(((G - poses.P) * np.conj(v)).imag), poses):
        return None
    return Dyad("RP", G=G, angle=float(phi), source=("phi", float(phi), s))


def resolve(poses: Poses, dyad: Dyad, betas=None):
    """Re-solve a dyad from the same free choices for new poses. With 4 or
    5 poses the choice is first moved onto what works there (the
    center-point curve, a Burmester point, a working slider direction); the
    dyad keeps the original choice as its source, so it can be followed."""
    from . import burmester

    tag = dyad.source[0] if dyad.source else None
    d = None
    if tag == "G":
        G = burmester.snap_ground(poses, dyad.source[1])
        d = None if G is None else rr_from_ground(poses, G, dyad.source[2])
    elif tag == "timed":
        d = rr_from_timing(poses, betas, dyad.source[1]) if betas is not None else None
    elif tag in ("gamma", "phi"):
        kind = "PR" if tag == "gamma" else "RP"
        ang = burmester.snap_direction(poses, kind, dyad.source[1])
        fn = pr_from_direction if kind == "PR" else rp_from_direction
        d = None if ang is None else fn(poses, ang, dyad.source[2])
    if d is None:
        return None
    return replace(d, source=dyad.source)
