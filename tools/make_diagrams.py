"""Generate the concept diagrams for the help docs (SVG) from the real
geometry code, so the pictures always match what the app computes.

    .venv/bin/python tools/make_diagrams.py
"""

import math
from pathlib import Path

import numpy as np

from kinsyn.core.analysis import analyze, circuit_derivatives, mechanical_advantage
from kinsyn.core.families import FourBar, SliderCrank
from kinsyn.core.target import Body, Keyframe, Target

OUT = Path(__file__).resolve().parents[1] / "kinsyn/help/docs/img"

# Drawn on a light card so they read the same in light and dark themes.
BG = "#f7f8fa"
INK = "#2b3340"
MUTED = "#8a93a3"
LINK = "#4a5568"
COUPLER = "#e08a2c"
CURVE = "#2f8fd8"
GOOD = "#2e9e5b"
BAD = "#d64545"
GHOST = "#8e6fd1"


class Svg:
    def __init__(self, w, h, xlim, ylim):
        self.w, self.h = w, h
        (x0, x1), (y0, y1) = xlim, ylim
        s = min(w / (x1 - x0), h / (y1 - y0))
        self.s = s
        self.ox = (w - s * (x1 - x0)) / 2 - s * x0
        self.oy = (h - s * (y1 - y0)) / 2 + s * y1
        self.parts = []

    def P(self, z):
        return self.ox + self.s * z.real, self.oy - self.s * z.imag

    def _pts(self, zs):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in (self.P(z) for z in zs))

    def line(self, zs, color=LINK, width=5, dash=None, cap="round", opacity=1.0):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<polyline points="{self._pts(zs)}" fill="none" stroke="{color}" stroke-width="{width}"'
                          f' stroke-linecap="{cap}" stroke-linejoin="round" opacity="{opacity}"{d}/>')

    def poly(self, zs, color=COUPLER, fill_opacity=0.18, width=3):
        self.parts.append(f'<polygon points="{self._pts(zs)}" fill="{color}" fill-opacity="{fill_opacity}"'
                          f' stroke="{color}" stroke-width="{width}" stroke-linejoin="round"/>')

    def pin(self, z, r=6):
        x, y = self.P(z)
        self.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{BG}" stroke="{INK}" stroke-width="2.5"/>')

    def dot(self, z, color=CURVE, r=6):
        x, y = self.P(z)
        self.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}"/>')

    def ground(self, z):
        x, y = self.P(z)
        tri = f"{x:.1f},{y:.1f} {x - 13:.1f},{y + 20:.1f} {x + 13:.1f},{y + 20:.1f}"
        self.parts.append(f'<polygon points="{tri}" fill="{MUTED}" fill-opacity="0.35" stroke="{MUTED}" stroke-width="2"/>')
        for k in range(5):
            hx = x - 16 + 8 * k
            self.parts.append(f'<line x1="{hx:.1f}" y1="{y + 20:.1f}" x2="{hx - 6:.1f}" y2="{y + 27:.1f}"'
                              f' stroke="{MUTED}" stroke-width="1.5"/>')
        self.pin(z)

    def text(self, z, s, color=INK, size=15, anchor="middle", dx=0, dy=0, weight="normal"):
        x, y = self.P(z)
        self.parts.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" fill="{color}" font-size="{size}"'
                          f' font-family="sans-serif" text-anchor="{anchor}" font-weight="{weight}">{s}</text>')

    def label(self, x, y, s, color=INK, size=15, anchor="start", weight="normal"):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-family="sans-serif"'
                          f' text-anchor="{anchor}" font-weight="{weight}">{s}</text>')

    def arc(self, c, r, a0, a1, color=GOOD, width=2.5):
        ts = np.linspace(a0, a1, 40)
        self.line(c + r * np.exp(1j * ts), color, width)

    def arrow(self, a, b, color=INK, width=2.5, head=0.18):
        self.line([a, b], color, width)
        u = (b - a) / abs(b - a)
        L = head * abs(b - a)
        self.line([b - L * u * np.exp(0.4j), b, b - L * u * np.exp(-0.4j)], color, width)

    def raw(self, s):
        self.parts.append(s)

    def save(self, name):
        OUT.mkdir(parents=True, exist_ok=True)
        body = "\n".join(self.parts)
        (OUT / name).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}">\n<rect x="0" y="0" width="{self.w}" height="{self.h}" rx="10" fill="{BG}"/>\n'
            f"{body}\n</svg>\n")


def frame(m, q, branch=None):
    return {k: v[0] for k, v in m.solve(np.array([q]), branch).points.items()}


def coupler_curve(m):
    _, _, c, _ = analyze(m)
    return c.frames.points["P"]


def draw_fourbar(svg, m, q, curve=True, labels=True):
    p = frame(m, q)
    if curve:
        svg.line(np.append(coupler_curve(m), coupler_curve(m)[:1]), CURVE, 2, dash="6 5")
    svg.line([p["A0"], p["B0"]], MUTED, 2.5, dash="8 6")
    svg.line([p["A0"], p["A"]])
    svg.line([p["B0"], p["B"]])
    svg.poly([p["A"], p["B"], p["P"]])
    svg.ground(p["A0"])
    svg.ground(p["B0"])
    svg.pin(p["A"])
    svg.pin(p["B"])
    svg.dot(p["P"])
    return p


def anatomy():
    m = FourBar(B0=100, a=30, b=85, c=60, P=45 + 30j)
    svg = Svg(620, 380, (-45, 150), (-35, 110))
    p = draw_fourbar(svg, m, math.radians(70))
    svg.text((p["A0"] + p["B0"]) / 2, "ground (fixed frame)", MUTED, dy=34)
    svg.text((p["A0"] + p["A"]) / 2, "input link / crank (a)", INK, anchor="end", dx=-12)
    svg.text((p["B0"] + p["B"]) / 2, "output link / rocker (c)", INK, anchor="start", dx=14)
    svg.text((p["A"] + p["B"]) / 2, "coupler (b)", COUPLER, dy=26, weight="bold")
    svg.text(p["P"], "coupler point P", CURVE, dy=-14, weight="bold")
    svg.text(p["A0"], "A0", INK, dx=-18, dy=5)
    svg.text(p["B0"], "B0", INK, dx=20, dy=5)
    svg.text(p["A"], "A", INK, dx=-14, dy=-6)
    svg.text(p["B"], "B", INK, dx=14, dy=-6)
    svg.label(20, 365, "dashed blue: the coupler curve traced by P", CURVE, 13)
    svg.save("fourbar-anatomy.svg")


def transmission():
    svg = Svg(700, 330, (-10, 300), (-45, 110))
    for x0, q, title, good in ((0, math.radians(95), "good: μ ≈ 90°", True),
                               (160, math.radians(205), "poor: μ small", False)):
        m = FourBar(A0=complex(x0, 0), B0=complex(x0 + 100, 0), a=30, b=85, c=60, P=40 + 0j)
        p = frame(m, q)
        svg.line([p["A0"], p["B0"]], MUTED, 2, dash="8 6")
        svg.line([p["A0"], p["A"]])
        svg.line([p["A"], p["B"]], COUPLER, 5)
        svg.line([p["B0"], p["B"]])
        svg.ground(p["A0"])
        svg.ground(p["B0"])
        svg.pin(p["A"])
        svg.pin(p["B"])
        a1, a2 = np.angle(p["A"] - p["B"]), np.angle(p["B0"] - p["B"])
        if (a2 - a1) % (2 * math.pi) > math.pi:
            a1, a2 = a2, a1
        a2 = a1 + (a2 - a1) % (2 * math.pi)
        col = GOOD if good else BAD
        svg.arc(p["B"], 16, a1, a2, col, 3)
        svg.text(p["B"] + 26 * np.exp(1j * (a1 + a2) / 2), "μ", col, size=18, dy=6, weight="bold")
        svg.text(complex(x0 + 50, 0), title, col, dy=58, weight="bold")
    svg.label(20, 318, "μ = angle between the coupler (orange) and the output link, measured at B", MUTED, 13)
    svg.save("transmission-angle.svg")


def grashof():
    cases = [("Crank-rocker", FourBar(B0=100, a=30, b=85, c=60, P=45 + 30j)),
             ("Double-crank", FourBar(B0=30, a=70, b=80, c=90, P=40 + 30j)),
             ("Double-rocker", FourBar(B0=100, a=80, b=30, c=90, P=15 + 25j)),
             ("Triple-rocker", FourBar(B0=100, a=70, b=60, c=80, P=30 + 30j))]
    svg = Svg(760, 262, (0, 760), (0, 262))
    for i, (name, m) in enumerate(cases):
        iv, full, c, s = analyze(m)
        pts = [v for k, v in c.frames.points.items() if not k.startswith("dir:")]
        z = np.concatenate(pts)
        cx, cy = (z.real.min() + z.real.max()) / 2, (z.imag.min() + z.imag.max()) / 2
        size = max(np.ptp(z.real), np.ptp(z.imag))
        k = 170 / size
        off = complex(95 + 190 * i, 132)
        T = lambda w: off + (w - complex(cx, cy)) * k
        A = c.frames.points["A"]
        svg.line(T(np.append(A, A[:1] if full else A[:0])), GOOD if full else BAD, 2.5, dash=None if full else "5 4")
        P = c.frames.points["P"]
        svg.line(T(np.append(P, P[:1])), CURVE, 1.5, dash="5 4")
        j = len(A) // 3
        p = {kk: v[j] for kk, v in c.frames.points.items()}
        svg.line(T(np.array([p["A0"], p["A"]])), LINK, 4)
        svg.line(T(np.array([p["B0"], p["B"]])), LINK, 4)
        svg.poly(T(np.array([p["A"], p["B"], p["P"]])), COUPLER, 0.18, 2.5)
        for g in ("A0", "B0"):
            svg.pin(T(p[g]), 5)
        svg.label(off.real, 26, name, INK, 15, "middle", "bold")
        svg.label(off.real, 248, "input rotates" if full else "input rocks", GOOD if full else BAD, 13, "middle")
    svg.save("grashof-classes.svg")


def toggle():
    m = FourBar(B0=80, a=30, b=60, c=55, P=30 + 0j)
    svg = Svg(640, 340, (-50, 125), (-35, 85))
    qt = math.radians(37.17)
    p = frame(m, qt)
    o = frame(m, math.radians(-40))
    svg.line([o["A0"], o["A"], o["B"], o["B0"]], MUTED, 3, dash="6 5", opacity=0.7)
    svg.text(o["A"], "open", MUTED, dx=-26, dy=6)
    svg.line([p["A0"], p["B0"]], MUTED, 2, dash="8 6")
    svg.line([p["A0"], p["A"]])
    svg.line([p["A"], p["B"]], COUPLER, 5)
    svg.line([p["B0"], p["B"]])
    svg.ground(p["A0"])
    svg.ground(p["B0"])
    svg.pin(p["A"])
    svg.pin(p["B"])
    stop_dir = np.exp(1j * math.radians(47))
    svg.line([p["A0"] + 20 * stop_dir, p["A0"] + 44 * stop_dir], BAD, 3, dash="2 3")
    svg.dot(p["A0"] + 44 * stop_dir, BAD, 5)
    svg.text(p["A0"] + 44 * stop_dir, "stop", BAD, dx=-10, dy=-12, anchor="end")
    svg.arc(p["A0"], 16, qt, math.radians(47), GOOD, 3)
    svg.text(p["B"], "toggle: input link and coupler in one line", INK, dy=-16, anchor="end", weight="bold")
    svg.text(p["A0"], "over-center", GOOD, size=13, dx=-24, dy=-26, anchor="end")
    svg.label(20, 326, "Push on the output and the linkage presses harder against the stop instead of opening.",
              MUTED, 13)
    svg.save("toggle-over-center.svg")


def slider():
    m = SliderCrank(a=30, b=100, e=20, P=50 + 20j)
    svg = Svg(640, 300, (-40, 150), (-40, 70))
    p = frame(m, math.radians(55))
    svg.line([complex(-35, 20), complex(145, 20)], MUTED, 2, dash="8 6")
    svg.text(complex(145, 20), "slider axis", MUTED, anchor="end", dy=-8)
    svg.line([p["A0"], p["A"]])
    svg.poly([p["A"], p["B"], p["P"]])
    box = [p["B"] + d for d in (-9 - 6j, 9 - 6j, 9 + 6j, -9 + 6j)]
    svg.poly(box, LINK, 0.25, 2.5)
    svg.ground(p["A0"])
    svg.pin(p["A"])
    svg.pin(p["B"])
    svg.dot(p["P"])
    svg.line([p["A0"], complex(0, 20)], BAD, 2, dash="3 3")
    svg.text(complex(0, 10), "e", BAD, dx=-12, weight="bold")
    svg.text((p["A0"] + p["A"]) / 2, "crank a", INK, anchor="start", dx=14, dy=10)
    svg.text((p["A"] + p["B"]) / 2, "coupler b", COUPLER, dy=-12)
    svg.text(p["B"], "slider", INK, dy=30)
    svg.label(20, 290, "e = offset of the slider axis from the crank pivot (0 = in-line)", MUTED, 13)
    svg.save("slider-crank.svg")


def assemblies():
    svg = Svg(680, 300, (-20, 300), (-85, 90))
    for x0, br, name in ((0, 1, "assembly +1"), (170, -1, "assembly −1")):
        m = FourBar(A0=complex(x0, 0), B0=complex(x0 + 100, 0), a=30, b=85, c=60, P=45 + 30j, branch=br)
        p = frame(m, math.radians(70))
        svg.line([p["A0"], p["B0"]], MUTED, 2, dash="8 6")
        svg.line([p["A0"], p["A"]])
        svg.line([p["B0"], p["B"]])
        svg.poly([p["A"], p["B"], p["P"]])
        svg.ground(p["A0"])
        svg.ground(p["B0"])
        svg.pin(p["A"])
        svg.pin(p["B"])
        svg.text(complex(x0 + 50, 0), name, INK, dy=64, weight="bold")
    svg.label(20, 270, "Same link lengths, same input angle: two different ways to assemble the linkage.", MUTED, 13)
    svg.save("assemblies.svg")


def poses_body():
    body = Body([[-12 - 6j, 22 - 6j, 22 + 7j, -12 + 7j]])
    ks = [Keyframe(0j, 0.0), Keyframe(55 + 30j, math.radians(35)), Keyframe(115 + 35j, math.radians(80))]
    svg = Svg(620, 320, (-30, 150), (-25, 95))
    svg.line([k.pos for k in ks], GHOST, 1.5, dash="3 5")
    for i, k in enumerate(ks):
        for pl in body.at(k.pos, k.angle):
            svg.poly(list(pl), GHOST, 0.12, 2)
        tip = k.pos + 26 * np.exp(1j * k.angle)
        svg.arrow(k.pos, tip, GHOST, 2.5, 0.3)
        svg.dot(k.pos, GHOST, 6)
        svg.text(k.pos, str(i + 1), GHOST, dx=-14, dy=-10, weight="bold")
    svg.text(ks[0].pos, "dot = position (drag to move)", INK, size=13, dy=34, anchor="start", dx=-20)
    svg.text(ks[2].pos + 26 * np.exp(1j * ks[2].angle), "arrow tip = angle (drag to rotate)", INK, size=13,
             anchor="end", dx=-12, dy=4)
    svg.label(20, 308, "Each pose is a ghost copy of the body you drew, placed where the part must be.", MUTED, 13)
    svg.save("poses-and-body.svg")


def snapping():
    svg = Svg(760, 230, (0, 760), (0, 230))
    for i, (title, note) in enumerate((("Grid", "rounds to the grid"), ("Point", "jumps onto a point"),
                                       ("Alignment", "lines up with a point"), ("Angle (Shift)", "15° steps"))):
        ox = 20 + 185 * i
        svg.raw(f'<rect x="{ox}" y="40" width="170" height="150" rx="8" fill="none" stroke="{MUTED}" stroke-opacity="0.4"/>')
        svg.label(ox + 85, 28, title, INK, 15, "middle", "bold")
        svg.label(ox + 85, 212, note, MUTED, 13, "middle")
        for gx in range(ox + 20, ox + 170, 25):
            svg.raw(f'<line x1="{gx}" y1="45" x2="{gx}" y2="185" stroke="{MUTED}" stroke-opacity="0.18"/>')
        for gy in range(55, 190, 25):
            svg.raw(f'<line x1="{ox + 5}" y1="{gy}" x2="{ox + 165}" y2="{gy}" stroke="{MUTED}" stroke-opacity="0.18"/>')
        cur = lambda x, y: svg.raw(f'<path d="M{x},{y} l0,16 l4,-4 l5,9 l3,-2 l-5,-8 l6,0 z" fill="{INK}"/>')
        mark = lambda x, y: svg.raw(f'<rect x="{x - 6}" y="{y - 6}" width="12" height="12" fill="none" stroke="{GOOD}" stroke-width="2.5"/>')
        if i == 0:
            cur(ox + 80, 112)
            mark(ox + 70, 105)
        elif i == 1:
            svg.raw(f'<circle cx="{ox + 110}" cy="{80}" r="6" fill="{GHOST}"/>')
            cur(ox + 118, 88)
            mark(ox + 110, 80)
        elif i == 2:
            svg.raw(f'<circle cx="{ox + 45}" cy="{70}" r="6" fill="{GHOST}"/>')
            svg.raw(f'<line x1="{ox + 45}" y1="70" x2="{ox + 45}" y2="150" stroke="{GOOD}" stroke-dasharray="5 4" stroke-width="1.5"/>')
            cur(ox + 49, 152)
            mark(ox + 45, 150)
        else:
            svg.raw(f'<circle cx="{ox + 35}" cy="{165}" r="6" fill="{GHOST}"/>')
            x2, y2 = ox + 35 + 110 * math.cos(math.radians(45)), 165 - 110 * math.sin(math.radians(45))
            svg.raw(f'<line x1="{ox + 35}" y1="165" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{GOOD}" stroke-dasharray="5 4" stroke-width="1.5"/>')
            svg.label(ox + 72, 158, "45°", GOOD, 13)
            cur(x2 - 18, y2 + 14)
            mark(x2 - 22, y2 + 22)
    svg.save("snapping.svg")


def motion_plots():
    m = FourBar(B0=100, a=30, b=85, c=60, P=45 + 30j)
    _, _, c, _ = analyze(m)
    d = circuit_derivatives(m, c, 2 * math.pi)  # 60 rpm
    out = np.degrees(np.unwrap(c.frames.output))
    series = [("output angle (deg)", out, CURVE), ("output velocity (deg/s)", np.degrees(d["output_vel"]), GOOD),
              ("output acceleration (deg/s²)", np.degrees(d["output_acc"]), BAD)]
    W, H = 720, 360
    svg = Svg(W, H, (0, W), (0, H))
    for i, (name, y, col) in enumerate(series):
        top = 20 + i * 112
        x = np.linspace(60, W - 20, len(y))
        lo, hi = y.min(), y.max()
        yy = top + 85 - (y - lo) / (hi - lo) * 80
        svg.raw(f'<line x1="60" y1="{top + 45}" x2="{W - 20}" y2="{top + 45}" stroke="{MUTED}" stroke-opacity="0.3"/>')
        pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, yy))
        svg.raw(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        svg.label(64, top + 8, name, col, 13, weight="bold")
    svg.label(W / 2, H - 4, "one crank revolution at 60 rpm (crank-rocker template)", MUTED, 12, "middle")
    svg.save("velocity-acceleration.svg")


def mech_advantage():
    m = SliderCrank(a=30, b=90, P=45 + 0j)
    _, _, c, _ = analyze(m)
    ma = mechanical_advantage(m, c)
    W, H = 700, 240
    svg = Svg(W, H, (0, W), (0, H))
    y = np.log10(np.clip(ma, 1e-2, 1e2))
    x = np.linspace(60, W - 20, len(y))
    yy = 190 - (y + 2) / 4 * 160
    for v, lab in ((-1, "0.1"), (0, "1"), (1, "10"), (2, "100")):
        gy = 190 - (v + 2) / 4 * 160
        svg.raw(f'<line x1="60" y1="{gy:.0f}" x2="{W - 20}" y2="{gy:.0f}" stroke="{MUTED}" stroke-opacity="0.25"/>')
        svg.label(52, gy + 4, lab, MUTED, 12, "end")
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(x, yy))
    svg.raw(f'<polyline points="{pts}" fill="none" stroke="{CURVE}" stroke-width="2.5"/>')
    svg.label(64, 22, "mechanical advantage (log scale), toggle press over one crank turn", INK, 13, weight="bold")
    svg.label(W / 2, 225, "spikes = toggle positions: huge force, almost no output motion", BAD, 13, "middle")
    svg.save("mechanical-advantage.svg")


def timeline():
    W, H = 700, 130
    svg = Svg(W, H, (0, W), (0, H))
    svg.raw(f'<rect x="30" y="50" width="{W - 60}" height="14" rx="4" fill="#ffffff" stroke="{MUTED}"/>')
    for deg in range(0, 361, 45):
        x = 30 + deg / 360 * (W - 60)
        svg.label(x, 82, f"{deg}°", MUTED, 12, "middle")
    for i, (deg, fixed) in enumerate(((40, False), (130, True), (205, False), (290, True))):
        x = 30 + deg / 360 * (W - 60)
        fill = "#e0a800" if fixed else "none"
        stroke = "#e0a800" if fixed else GHOST
        svg.raw(f'<circle cx="{x:.0f}" cy="57" r="7" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>')
        svg.label(x, 40, str(i + 1), stroke, 14, "middle", "bold")
    svg.label(30, 112, "hollow = free timing (solver decides)    solid = prescribed input angle", INK, 13)
    svg.save("timeline.svg")


if __name__ == "__main__":
    for fn in (anatomy, transmission, grashof, toggle, slider, assemblies, poses_body, snapping, motion_plots,
               mech_advantage, timeline):
        fn()
    print("wrote", sorted(p.name for p in OUT.glob("*.svg")))
