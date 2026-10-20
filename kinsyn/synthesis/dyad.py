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
from dataclasses import dataclass

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


def _rows_re(c):
    """Row for Re[c z] as a linear form in (z.real, z.imag)."""
    return np.array([c.real, -c.imag])


def _rows_im(c):
    """Row for Im[c z]."""
    return np.array([c.imag, c.real])


def _solve_linear(rows, rhs, ref, s=0.0, scale=1.0):
    """Solve rows @ (x, y) = rhs for a complex z.

    Two independent rows: the unique solution. One row (two poses): the
    point on the solution line nearest `ref`, moved by `s` along the line.
    Returns None when the system is degenerate."""
    A = np.asarray(rows, float).reshape(-1, 2)
    b = np.asarray(rhs, float)
    if len(A) >= 2:
        A2, b2 = A[:2], b[:2]
        det = A2[0, 0] * A2[1, 1] - A2[0, 1] * A2[1, 0]
        if abs(det) < DEGENERATE * max(1.0, np.abs(A2).max()) ** 2:
            return None
        x, y = np.linalg.solve(A2, b2)
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


def rr_from_ground(poses: Poses, G, s=0.0):
    """RR dyad with ground pin G: the body point that stays at a constant
    distance from G (|M_j - G| equal for all poses). Linear in m."""
    u = poses.P - G
    a = poses.a
    rows, rhs = [], []
    for j in range(1, min(len(poses), 3)):
        c = 2 * (np.conj(u[j]) * a[j] - np.conj(u[0]) * a[0])
        rows.append(_rows_re(c))
        rhs.append(abs(u[0]) ** 2 - abs(u[j]) ** 2)
    # Two poses: start from the point of the solution line nearest the body origin.
    m = _solve_linear(rows, rhs, 0j, s, poses.scale())
    if m is None:
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
    all lie on one line of that direction. Linear in m."""
    w = np.exp(-1j * gamma)
    a = poses.a
    rows, rhs = [], []
    for j in range(1, min(len(poses), 3)):
        rows.append(_rows_im((a[j] - a[0]) * w))
        rhs.append(-((poses.P[j] - poses.P[0]) * w).imag)
    m = _solve_linear(rows, rhs, 0j, s, poses.scale())
    if m is None:
        return None
    return Dyad("PR", m=m, angle=float(gamma), source=("gamma", float(gamma), s))


def rp_from_direction(poses: Poses, phi, s=0.0):
    """RP dyad whose body slides along direction phi (body frame) through
    a ground swivel G: G keeps the same distance from the slide line in
    every pose. Linear in G, and independent of where the line sits on the
    body (that only changes the offset)."""
    v = np.exp(1j * (phi + poses.th))
    rows, rhs = [], []
    for j in range(1, min(len(poses), 3)):
        rows.append(_rows_im(np.conj(v[j]) - np.conj(v[0])))
        rhs.append((poses.P[j] * np.conj(v[j])).imag - (poses.P[0] * np.conj(v[0])).imag)
    G = _solve_linear(rows, rhs, complex(np.mean(poses.P)), s, poses.scale())
    if G is None:
        return None
    return Dyad("RP", G=G, angle=float(phi), source=("phi", float(phi), s))


def resolve(poses: Poses, dyad: Dyad, betas=None):
    """Re-solve a dyad from the same free choices for new poses."""
    tag = dyad.source[0] if dyad.source else None
    if tag == "G":
        return rr_from_ground(poses, dyad.source[1], dyad.source[2])
    if tag == "timed":
        return rr_from_timing(poses, betas, dyad.source[1]) if betas is not None else None
    if tag == "gamma":
        return pr_from_direction(poses, dyad.source[1], dyad.source[2])
    if tag == "phi":
        return rp_from_direction(poses, dyad.source[1], dyad.source[2])
    return None
