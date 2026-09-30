"""Closed-form position solutions for the single-loop R/P linkage families."""

import math
from dataclasses import dataclass

import numpy as np

from .mechanism import Drawing, Frames, Mechanism, Param, angle_between, register

TOL = 1e-9


def circle_intersect(c1, r1, c2, r2, sigma):
    """Intersection of circle(c1, r1) and circle(c2, r2), vectorised.

    sigma=+1 picks the point to the left of the directed line c1 -> c2,
    sigma=-1 the right one. NaN where the circles do not meet."""
    dv = c2 - c1
    d = np.abs(dv)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
        h2 = r1 * r1 - x * x
        h2 = np.where((h2 < 0) & (h2 > -TOL * np.maximum(r1, r2) ** 2), 0.0, h2)
        return c1 + (x + 1j * sigma * np.sqrt(h2)) * (dv / d)


def _const(z, q):
    return np.full(np.shape(q), z, dtype=complex)


def _sqrt_clamped(v2, scale):
    v2 = np.where((v2 < 0) & (v2 > -TOL * scale * scale), 0.0, v2)
    with np.errstate(invalid="ignore"):
        return np.sqrt(v2)


def _choose(sigma, branch):
    return sigma if branch is None else branch


# --------------------------------------------------------------------------
@register
@dataclass
class FourBar(Mechanism):
    kind = "fourbar"
    title = "Four-bar (RRRR)"
    params = (
        Param("A0", "Input pivot A0", "point"),
        Param("B0", "Output pivot B0", "point"),
        Param("a", "Input link a", "length"),
        Param("b", "Coupler b", "length"),
        Param("c", "Output link c", "length"),
        Param("P", "Coupler point (along AB, left of AB)", "point"),
        Param("branch", "Assembly", "branch"),
    )

    A0: complex = 0j
    B0: complex = 100 + 0j
    a: float = 40.0
    b: float = 120.0
    c: float = 80.0
    P: complex = 60 + 40j
    branch: int = 1

    def solve(self, q, branch=None):
        q = np.asarray(q, float)
        A = self.A0 + self.a * np.exp(1j * q)
        B = circle_intersect(A, self.b, _const(self.B0, q), self.c, _choose(self.branch, branch))
        u = (B - A) / self.b
        return Frames(
            q=q,
            points={"A0": _const(self.A0, q), "B0": _const(self.B0, q), "A": A, "B": B,
                    "P": A + self.P * u},
            mu=angle_between(A - B, self.B0 - B),
            output=np.angle(B - self.B0),
            ok=np.isfinite(B),
        )

    def input_domain(self):
        return 0.0, 2 * math.pi, True

    def ground_length(self):
        return abs(self.B0 - self.A0)

    def scale(self):
        return max(self.a, self.b, self.c, self.ground_length(), abs(self.P))

    @property
    def output_label(self):
        return "Output link angle"

    def drawing(self):
        return Drawing(links=[("A0", "A"), ("A", "B", "P"), ("B0", "B")],
                       ground=["A0", "B0"], pins=["A", "B"], coupler=("A", "B", "P"))

    def toggle_links(self):
        return ("A0", "A", "B")

    def classify(self):
        return classify_fourbar(self.ground_length(), self.a, self.b, self.c)


def classify_fourbar(g, a, b, c):
    """Grashof classification with input link a, coupler b, output link c."""
    links = {"ground": g, "input": a, "coupler": b, "output": c}
    order = sorted(links, key=lambda k: (links[k], ["ground", "input", "output", "coupler"].index(k)))
    s, l = links[order[0]], links[order[-1]]
    pq = sum(links[k] for k in order[1:3])
    eps = 1e-6 * l
    notes = []
    if abs(a - c) < eps and abs(b - g) < eps:
        notes.append("Parallelogram / antiparallelogram proportions (a = c, b = ground)")
    elif (abs(a - g) < eps and abs(b - c) < eps) or (abs(a - b) < eps and abs(c - g) < eps):
        notes.append("Deltoid (kite) proportions")
    if abs(s + l - pq) < eps:
        notes.append("s + l = p + q: can flip between assemblies at the change point")
        return "Change point (Grashof boundary)", notes
    if s + l > pq:
        notes.append("s + l > p + q: no link can fully rotate")
        return "Triple-rocker (non-Grashof)", notes
    notes.append("s + l < p + q (Grashof)")
    return {
        "ground": "Double-crank (drag link)",
        "input": "Crank-rocker",
        "output": "Rocker-crank",
        "coupler": "Double-rocker (Grashof)",
    }[order[0]], notes


# --------------------------------------------------------------------------
@register
@dataclass
class SliderCrank(Mechanism):
    kind = "slider_crank"
    title = "Slider-crank (RRRP)"
    params = (
        Param("A0", "Crank pivot A0", "point"),
        Param("a", "Crank a", "length"),
        Param("b", "Coupler b", "length"),
        Param("gamma", "Slider axis angle", "angle"),
        Param("e", "Slider offset e", "signed_length"),
        Param("P", "Coupler point (along AB, left of AB)", "point"),
        Param("branch", "Assembly", "branch"),
        Param("driver", "Input", "choice", ("crank", "slider")),
    )

    A0: complex = 0j
    a: float = 40.0
    b: float = 120.0
    gamma: float = 0.0
    e: float = 0.0
    P: complex = 60 + 20j
    branch: int = 1
    driver: str = "crank"

    def solve(self, q, branch=None):
        q = np.asarray(q, float)
        sigma = _choose(self.branch, branch)
        ug = np.exp(1j * self.gamma)
        if self.driver == "crank":
            A = self.A0 + self.a * np.exp(1j * q)
            Al = (A - self.A0) / ug
            x = Al.real + sigma * _sqrt_clamped(self.b ** 2 - (self.e - Al.imag) ** 2, self.b)
            B = self.A0 + (x + 1j * self.e) * ug
            output = x
            mu = math.pi / 2 - _acute(np.angle((B - A) / ug))
        else:
            B = self.A0 + (q + 1j * self.e) * ug
            A = circle_intersect(_const(self.A0, q), self.a, B, self.b, sigma)
            output = np.angle(A - self.A0)
            mu = angle_between(B - A, self.A0 - A)
        u = (B - A) / self.b
        return Frames(
            q=q,
            points={"A0": _const(self.A0, q), "A": A, "B": B, "P": A + self.P * u},
            mu=mu, output=output, ok=np.isfinite(A) & np.isfinite(B),
        )

    @property
    def input_kind(self):
        return "angle" if self.driver == "crank" else "length"

    @property
    def output_kind(self):
        return "length" if self.driver == "crank" else "angle"

    @property
    def output_label(self):
        return "Slider position" if self.driver == "crank" else "Crank angle"

    def input_domain(self):
        if self.driver == "crank":
            return 0.0, 2 * math.pi, True
        r = self.a + self.b + abs(self.e) + 1.0
        return -r, r, False

    def scale(self):
        return max(self.a, self.b, abs(self.e), abs(self.P))

    def drawing(self):
        ug = np.exp(1j * self.gamma)
        rail_c = self.A0 + 1j * self.e * ug
        return Drawing(links=[("A0", "A"), ("A", "B", "P")], ground=["A0"], pins=["A", "B"],
                       blocks=[("B", self.gamma)],
                       rails=[(rail_c, self.gamma, self.a + self.b + abs(self.e))],
                       coupler=("A", "B", "P"))

    def toggle_links(self):
        return ("A0", "A", "B")

    def classify(self):
        rotates = self.b >= self.a + abs(self.e) - 1e-9
        notes = [f"crank rotates fully when b >= a + |e|  ({'yes' if rotates else 'no'})"]
        notes.append("in-line (e = 0)" if abs(self.e) < 1e-9 else "offset: unequal stroke times (quick return)")
        if self.driver == "slider":
            return "Slider-driven crank (linear input)", notes
        return ("Slider-crank" if rotates else "Slider-crank (crank rocks)"), notes


def _acute(phi):
    """Acute angle (0..pi/2) between a line at angle phi and the x-axis."""
    p = np.abs(np.mod(phi + math.pi / 2, math.pi) - math.pi / 2)
    return p


# --------------------------------------------------------------------------
@register
@dataclass
class InvertedSliderCrank(Mechanism):
    """Crank A0-A; the body pinned at A slides along a line that passes at
    offset e from the ground pivot B0 (slotted lever, rod through a swivel
    block, or a hydraulic cylinder when driven by its stroke)."""

    kind = "inverted_slider"
    title = "Inverted slider-crank (RRPR / RPRR)"
    params = (
        Param("A0", "Crank pivot A0", "point"),
        Param("a", "Crank a", "length"),
        Param("B0", "Swivel / rocker pivot B0", "point"),
        Param("e", "Slide offset e", "signed_length"),
        Param("P", "Point on sliding body (from A, along slide)", "point"),
        Param("branch", "Assembly (stroke input only)", "branch"),
        Param("driver", "Input", "choice", ("crank", "stroke")),
    )

    A0: complex = 0j
    a: float = 40.0
    B0: complex = 100 + 0j
    e: float = 0.0
    P: complex = -30 + 0j
    branch: int = 1
    driver: str = "crank"

    def solve(self, q, branch=None):
        q = np.asarray(q, float)
        if self.driver == "crank":
            A = self.A0 + self.a * np.exp(1j * q)
        else:
            d = np.sqrt(q * q + self.e ** 2)
            A = circle_intersect(_const(self.A0, q), self.a, _const(self.B0, q), d,
                                 _choose(self.branch, branch))
        w = self.B0 - A
        d = np.abs(w)
        with np.errstate(invalid="ignore", divide="ignore"):
            phi = np.angle(w) - np.arcsin(self.e / d)
        u = np.exp(1j * phi)
        L = _sqrt_clamped(d * d - self.e ** 2, self.a)
        F = A + L * u
        ext = 0.3 * (self.a + abs(self.B0 - self.A0))
        return Frames(
            q=q,
            points={"A0": _const(self.A0, q), "B0": _const(self.B0, q), "A": A, "F": F,
                    "R": A + (L + ext) * u, "P": A + self.P * u, "dir:rod": u},
            # Crank input: force acts normal to the slide on the slotted link, whose
            # point at A moves normal to B0-A, so mu = 90 deg - asin(e/d).
            # Stroke input: the cylinder force acts along the slide on the crank.
            mu=(math.pi / 2 - np.abs(phi - np.angle(w)) if self.driver == "crank"
                else angle_between(u, A - self.A0)),
            output=phi if self.driver == "crank" else np.angle(A - self.A0),
            ok=np.isfinite(F),
        )

    @property
    def input_kind(self):
        return "angle" if self.driver == "crank" else "length"

    @property
    def output_label(self):
        return "Slotted link angle" if self.driver == "crank" else "Crank angle"

    @property
    def has_branches(self):
        return self.driver == "stroke"

    def input_domain(self):
        if self.driver == "crank":
            return 0.0, 2 * math.pi, True
        return 0.0, self.a + abs(self.B0 - self.A0) + abs(self.e) + 1.0, False

    def scale(self):
        return max(self.a, abs(self.B0 - self.A0), abs(self.e), abs(self.P))

    def drawing(self):
        links = [("A0", "A"), ("A", "R")]
        if abs(self.P) > 1e-9:
            links.append(("A", "P"))
        if abs(self.e) > 1e-9:
            links.append(("B0", "F"))
        return Drawing(links=links, ground=["A0", "B0"], pins=["A"],
                       blocks=[("F", "dir:rod")], coupler=("A", "R"))

    def classify(self):
        g = abs(self.B0 - self.A0)
        rotates = abs(g - self.a) >= abs(self.e) - 1e-9 and abs(g - self.a) > 1e-9
        notes = []
        if self.driver == "stroke":
            notes.append("linear actuator (cylinder) between B0 and the crank")
            return "Oscillating cylinder (stroke input)", notes
        notes.append(f"crank rotates fully when |ground - a| >= |e|  ({'yes' if rotates else 'no'})")
        if self.a > g:
            return "Whitworth quick-return (slotted link rotates)", notes
        return "Crank-shaper quick-return (slotted link rocks)", notes


# --------------------------------------------------------------------------
@register
@dataclass
class ScotchYoke(Mechanism):
    kind = "scotch_yoke"
    title = "Scotch yoke (RPPR)"
    params = (
        Param("A0", "Crank pivot A0", "point"),
        Param("a", "Crank a", "length"),
        Param("gamma", "Yoke travel angle", "angle"),
        Param("P", "Point on yoke (from yoke centre)", "point"),
    )

    A0: complex = 0j
    a: float = 40.0
    gamma: float = 0.0
    P: complex = 100 + 0j

    def solve(self, q, branch=None):
        q = np.asarray(q, float)
        ug = np.exp(1j * self.gamma)
        A = self.A0 + self.a * np.exp(1j * q)
        s = ((A - self.A0) / ug).real
        Y = self.A0 + s * ug
        half = 1.25 * self.a * 1j * ug
        return Frames(
            q=q,
            points={"A0": _const(self.A0, q), "A": A, "Y": Y, "S1": Y + half, "S2": Y - half,
                    "T": Y + 2.4 * self.a * ug, "P": Y + self.P * ug},
            mu=np.full(q.shape, math.pi / 2), output=s, ok=np.isfinite(A),
        )

    @property
    def output_kind(self):
        return "length"

    @property
    def output_label(self):
        return "Yoke position"

    @property
    def has_branches(self):
        return False

    def input_domain(self):
        return 0.0, 2 * math.pi, True

    def scale(self):
        return max(self.a, abs(self.P))

    def drawing(self):
        ug = np.exp(1j * self.gamma)
        return Drawing(links=[("A0", "A"), ("S1", "S2"), ("Y", "T"), ("Y", "P")],
                       ground=["A0"], pins=[], blocks=[("A", self.gamma + math.pi / 2)],
                       rails=[(self.A0 + 2.4 * self.a * ug, self.gamma, 1.4 * self.a)],
                       coupler=("S1", "S2"))

    def classify(self):
        return "Scotch yoke", ["pure simple-harmonic output: x = a cos(theta)"]


# --------------------------------------------------------------------------
@register
@dataclass
class EllipticalTrammel(Mechanism):
    kind = "trammel"
    title = "Elliptical trammel (PRRP)"
    params = (
        Param("O", "Guide intersection O", "point"),
        Param("gamma1", "Guide 1 angle", "angle"),
        Param("gamma2", "Guide 2 angle", "angle"),
        Param("b", "Coupler b", "length"),
        Param("P", "Coupler point (along B1B2, left)", "point"),
    )

    O: complex = 0j
    gamma1: float = 0.0
    gamma2: float = math.pi / 2
    b: float = 80.0
    P: complex = 120 + 0j

    def solve(self, q, branch=None):
        q = np.asarray(q, float)
        u1, u2 = np.exp(1j * self.gamma1), np.exp(1j * self.gamma2)
        z = self.b * np.exp(1j * q)
        cross = lambda p, r: (np.conj(p) * r).imag
        det = cross(-u1, u2)
        with np.errstate(invalid="ignore", divide="ignore"):
            t = cross(-u1, z) / det
            s1 = cross(z, u2) / det
        B1, B2 = self.O + s1 * u1, self.O + t * u2
        return Frames(
            q=q,
            points={"B1": B1, "B2": B2, "P": B1 + self.P * np.exp(1j * q)},
            mu=np.full(q.shape, np.nan), output=s1, ok=np.isfinite(B1) & np.isfinite(B2),
        )

    @property
    def output_kind(self):
        return "length"

    @property
    def output_label(self):
        return "Slider 1 position"

    @property
    def has_branches(self):
        return False

    def input_domain(self):
        return 0.0, 2 * math.pi, True

    def scale(self):
        return max(self.b, abs(self.P))

    def drawing(self):
        r = 1.2 * self.scale()
        return Drawing(links=[("B1", "B2", "P")], ground=[], pins=["B1", "B2"],
                       blocks=[("B1", self.gamma1), ("B2", self.gamma2)],
                       rails=[(self.O, self.gamma1, r), (self.O, self.gamma2, r)],
                       coupler=("B1", "B2", "P"))

    def classify(self):
        return "Elliptical trammel", ["coupler points trace ellipses; input is the coupler angle"]
