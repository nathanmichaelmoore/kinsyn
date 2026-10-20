"""Motion generation for 2 and 3 exact poses.

The poses fix the body; each dyad has one free choice (see dyad.py). The
solver samples those choices, pairs the dyads into mechanisms (four-bar,
slider-crank, inverted slider-crank), and checks every candidate by
re-running the analysis on it:

- it must reproduce the poses (round trip),
- all poses on one assembly (no branch defect),
- reached in order in one continuous motion (no order or circuit defect),
- transmission angle over the motion actually used,
- the input-motion option (any / full rotation / a Grashof class),
- change point, link length ratio and pivot zones.

Candidates that fail are kept with their reasons, so the GUI can show what
was ruled out and why."""

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from kinsyn.core.families import FourBar, InvertedSliderCrank, SliderCrank
from kinsyn.core.target import point_in_polygon

from . import burmester
from .dyad import Dyad, Poses, resolve, rr_from_timing

FAMILIES = {
    "fourbar": "Four-bar",
    "slider_crank": "Slider-crank",
    "inverted_slider": "Inverted slider-crank",
}

# key -> (label, test on (classification, full_rotation))
INPUT_MOTIONS = {
    "any": ("Any (rocking input allowed)", lambda cls, full: True),
    "full": ("Input must fully rotate", lambda cls, full: full),
    "crank-rocker": ("Crank-rocker", lambda cls, full: cls.startswith("Crank-rocker")),
    "double-crank": ("Double-crank (drag link)", lambda cls, full: cls.startswith("Double-crank")),
    "double-rocker": ("Double-rocker (Grashof)", lambda cls, full: cls.startswith("Double-rocker")),
    "triple-rocker": ("Triple-rocker (non-Grashof)", lambda cls, full: cls.startswith("Triple-rocker")),
}

TWO_PI = 2 * math.pi
CIRCUIT_DEFECT = "circuit defect: cannot move between the poses without taking it apart"


@dataclass
class Options:
    families: tuple = tuple(FAMILIES)
    input_motion: str = "any"
    mu_min: float = math.radians(40)
    max_ratio: float = 10.0
    allow_change_point: bool = False
    grid: int = 11  # ground pivot candidates per side
    directions: int = 24  # slider / slide directions tried
    curve_samples: int = 90  # points tried along a center-point curve (4 poses)
    max_results: int = 60
    budget: int = 3000  # most candidates checked in full per solve


@dataclass
class Candidate:
    mech: object
    dyads: tuple  # (input dyad, output dyad)
    q: np.ndarray  # input value at each pose
    body_angle: float  # body angle minus coupler angle (constant)
    lengths: tuple
    grounds: tuple  # ground pivot positions (complex)
    pivots: tuple = ()  # every pivot at pose 1, to tell designs apart
    reasons: list = field(default_factory=list)  # (category, text)
    classification: str = ""
    full_rotation: bool = False
    mu_min: float = float("nan")  # worst transmission quality between the poses (rad)
    operating: tuple | None = None  # input range from the first to the last pose
    error: float = float("nan")  # worst round-trip pose error (mm)
    checked: bool = False  # went through every check (not stopped early)

    @property
    def valid(self):
        return not self.reasons

    @property
    def ratio(self):
        return max(self.lengths) / min(self.lengths)

    @property
    def size(self):
        return max(self.lengths)

    @property
    def family(self):
        return self.mech.kind

    def input_name(self):
        """What drives it, e.g. "crank at A0" or "slider"."""
        kind = self.dyads[0].kind
        return {"RR": "crank", "PR": "slider", "RP": "cylinder"}[kind]

    def reject(self, category, text):
        self.reasons.append((category, text))

    def why(self):
        return "; ".join(text for _, text in self.reasons)


@dataclass
class Result:
    method: str = ""
    solutions: list = field(default_factory=list)
    rejected: list = field(default_factory=list)  # best rejected candidates
    reject_counts: Counter = field(default_factory=Counter)
    evaluated: int = 0
    combinations: int = 0
    notes: list = field(default_factory=list)
    # 4 and 5 poses: center-point / circle-point curves (burmester.Curves),
    # Burmester points (ground pivots) and working slider directions.
    curves: list = field(default_factory=list)
    burmester_points: list = field(default_factory=list)
    slider_dirs: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Building a mechanism from two dyads

def _ok_len(*v):
    return all(x > 1e-6 for x in v)


def build(poses: Poses, din: Dyad, dout: Dyad):
    """Mechanism from (input dyad, output dyad). Returns
    (mech, q at each pose, body_angle, link lengths, ground pivots) or None
    when the pair does not make a mechanism this module knows."""
    P1, th1 = poses.P[0], poses.th[0]
    pair = (din.kind, dout.kind)
    if pair == ("RR", "RR"):
        A, B = poses.world(din.m), poses.world(dout.m)
        A0, B0 = din.G, dout.G
        a, b, c, g = (float(abs(x)) for x in (A[0] - A0, B[0] - A[0], B[0] - B0, B0 - A0))
        if not _ok_len(a, b, c, g):
            return None
        u = (B[0] - A[0]) / b
        mech = FourBar(A0=A0, B0=B0, a=a, b=b, c=c, P=complex((P1 - A[0]) / u))
        return mech, np.angle(A - A0), th1 - float(np.angle(u)), (g, a, b, c), (A0, B0)
    if pair in (("RR", "PR"), ("PR", "RR")):
        crank, slide = (din, dout) if pair[0] == "RR" else (dout, din)
        A, B = poses.world(crank.m), poses.world(slide.m)
        A0, gamma = crank.G, slide.angle
        a, b = float(abs(A[0] - A0)), float(abs(B[0] - A[0]))
        if not _ok_len(a, b):
            return None
        ug = np.exp(1j * gamma)
        e = float(((B[0] - A0) / ug).imag)
        u = (B[0] - A[0]) / b
        driver = "crank" if pair[0] == "RR" else "slider"
        mech = SliderCrank(A0=A0, a=a, b=b, gamma=float(gamma), e=e, P=complex((P1 - A[0]) / u), driver=driver)
        q = np.angle(A - A0) if driver == "crank" else ((B - A0) / ug).real
        return mech, q, th1 - np.angle(u), (a, b), (A0,)
    if pair in (("RR", "RP"), ("RP", "RR")):
        crank, swivel = (din, dout) if pair[0] == "RR" else (dout, din)
        A = poses.world(crank.m)
        A0, B0 = crank.G, swivel.G
        a, g = float(abs(A[0] - A0)), float(abs(B0 - A0))
        if not _ok_len(a, g):
            return None
        # Slide line through A, pointing towards B0. If B0 is ahead of A in
        # some poses and behind it in others, the rod would have to pass
        # through its own swivel: not a usable design.
        vj = np.exp(1j * (swivel.angle + poses.th))
        ahead = ((B0 - A) * np.conj(vj)).real
        if not ((ahead > 0).all() or (ahead < 0).all()):
            return None
        v = vj[0] if ahead[0] > 0 else -vj[0]
        e = float(((B0 - A[0]) * np.conj(v)).imag)
        driver = "crank" if pair[0] == "RR" else "stroke"
        mech = InvertedSliderCrank(A0=A0, a=a, B0=B0, e=e, P=complex((P1 - A[0]) / v), driver=driver)
        if driver == "crank":
            q = np.angle(A - A0)
        else:
            q = np.sqrt(np.maximum(np.abs(B0 - A) ** 2 - e * e, 0.0))
        return mech, q, th1 - np.angle(v), (a, g), (A0, B0)
    return None


def _family_of(pair):
    return {("RR", "RR"): "fourbar", ("RR", "PR"): "slider_crank", ("PR", "RR"): "slider_crank",
            ("RR", "RP"): "inverted_slider", ("RP", "RR"): "inverted_slider"}.get(pair)


# --------------------------------------------------------------------------
# Checks

def _wrap(x):
    return (x + math.pi) % TWO_PI - math.pi


def _pose_errors(mech, q, poses, body_angle, branch, scale):
    f = mech.solve(q, branch)
    pos = np.abs(f.points["P"] - poses.P)
    ang = np.abs(_wrap(mech.coupler_angle(f) + body_angle - poses.th))
    err = pos + scale * ang
    return np.where(np.isfinite(err), err, np.inf)


def _segments(targets, per=24):
    """Input samples visiting `targets` in order."""
    parts = [np.linspace(targets[k], targets[k + 1], per, endpoint=False) for k in range(len(targets) - 1)]
    return np.concatenate(parts + [np.array([targets[-1]])])


def _paths(q, periodic, betas):
    """Candidate input paths through the poses, in order: list of target
    lists (unwrapped). Empty when the order cannot be kept."""
    if betas is not None:
        return [[q[0] + b for b in betas]]
    if not periodic:
        d = np.diff(q)
        return [list(q)] if (d > 0).all() or (d < 0).all() else []
    rel = np.mod(q - q[0], TWO_PI)
    rel[0] = 0.0
    out = []
    if (np.diff(rel) > 0).all():
        out.append(list(q[0] + rel))  # counter-clockwise
    back = np.where(rel > 0, rel - TWO_PI, 0.0)
    if (np.diff(back) < 0).all():
        out.append(list(q[0] + back))  # clockwise
    return out


def check(cand: Candidate, poses: Poses, opts: Options, zones=(), betas=None, quick=False):
    """Fill in the candidate's metrics and rejection reasons. Returns it.

    With `quick`, stop after the cheap geometric checks (ratio, zones) if
    those already reject it; `cand.checked` then stays False."""
    mech = cand.mech
    scale = max(poses.scale(), cand.size)
    tol = 1e-6 * scale

    if cand.ratio > opts.max_ratio:
        cand.reject("ratio", f"link length ratio {cand.ratio:.1f} is above {opts.max_ratio:g}")
    allowed = [z.polygon for z in zones if z.allow]
    banned = [z.polygon for z in zones if not z.allow]
    for G in cand.grounds:
        if allowed and not any(point_in_polygon(G, p) for p in allowed):
            cand.reject("zone", "ground pivot outside the allowed zone")
            break
        if any(point_in_polygon(G, p) for p in banned):
            cand.reject("zone", "ground pivot in a keep-out zone")
            break
    if quick and cand.reasons:
        return cand
    cand.checked = True

    # Which assembly reproduces each pose?
    if mech.has_branches:
        ep = _pose_errors(mech, cand.q, poses, cand.body_angle, 1, scale)
        em = _pose_errors(mech, cand.q, poses, cand.body_angle, -1, scale)
        okp, okm = ep < tol, em < tol
        if okp.all() or okm.all():
            branch = 1 if okp.all() and (not okm.all() or ep.max() <= em.max()) else -1
        else:
            branch = 1 if okp.sum() >= okm.sum() else -1
            if (okp | okm).all():
                cand.reject("branch defect", "branch defect: the poses are on different assemblies")
            else:
                cand.reject("error", "does not reproduce the poses")
        mech = mech.copy(branch=branch)
        cand.error = float((ep if branch == 1 else em).max())
    else:
        branch = None
        err = _pose_errors(mech, cand.q, poses, cand.body_angle, None, scale)
        cand.error = float(err.max())
        if not (err < tol).all():
            cand.reject("error", "does not reproduce the poses")
    cand.mech = mech

    name, _ = mech.classify()
    cand.classification = name
    lo, hi, periodic = mech.input_domain()
    if periodic:
        cand.full_rotation = bool(mech.solve(np.linspace(lo, hi, 145), branch).ok.all())
    if name.startswith("Change point") and not opts.allow_change_point:
        cand.reject("change point", "change point: can flip to the other assembly")
    label, test = INPUT_MOTIONS.get(opts.input_motion, INPUT_MOTIONS["any"])
    if not test(name, cand.full_rotation):
        cand.reject("input motion", f"input motion is not {label.lower()}" if opts.input_motion != "full"
                    else "input does not fully rotate")

    # Order and circuit: move through the poses in sequence on one assembly.
    best = None
    for targets in _paths(cand.q, periodic, betas):
        path = _segments(targets)
        f = mech.solve(path, branch)
        if not f.ok.all():
            continue
        mu = f.mu
        quality = np.minimum(mu, math.pi - mu)
        m = float(np.nanmin(quality)) if np.isfinite(quality).any() else float("nan")
        if best is None or (np.isfinite(m) and (not np.isfinite(best[0]) or m > best[0])):
            best = (m, path)
    if best is None:
        if periodic and betas is None and len(poses) >= 3:
            # Is it reachable the other way round (out of order)?
            q = cand.q
            rel = np.mod(q - q[0], TWO_PI)
            reverse = [q[0], q[0] + rel[-1]] if rel[1] > rel[-1] else [q[0], q[0] + rel[-1] - TWO_PI]
            if mech.solve(_segments(reverse), branch).ok.all():
                cand.reject("order defect", "order defect: the poses are not reached in sequence")
            else:
                cand.reject("circuit defect", CIRCUIT_DEFECT)
        elif betas is not None:
            cand.reject("timing", "cannot follow the prescribed timing without taking it apart")
        elif not periodic and not ((np.diff(cand.q) > 0).all() or (np.diff(cand.q) < 0).all()):
            cand.reject("order defect", "order defect: the poses are not reached in sequence")
        else:
            cand.reject("circuit defect", CIRCUIT_DEFECT)
    else:
        cand.mu_min, path = best
        cand.operating = (float(path.min()), float(path.max()))
        if np.isfinite(cand.mu_min) and cand.mu_min < opts.mu_min:
            cand.reject("transmission angle", f"transmission angle drops to {math.degrees(cand.mu_min):.0f}° "
                                              f"(limit {math.degrees(opts.mu_min):.0f}°)")
    return cand


def evaluate(poses: Poses, din: Dyad, dout: Dyad, opts: Options, zones=(), betas=None, quick=False):
    built = build(poses, din, dout)
    if built is None:
        return None
    mech, q, body_angle, lengths, grounds = built
    pivots = tuple(d.G for d in (din, dout) if d.G is not None) + \
        tuple(complex(poses.world(d.m)[0]) for d in (din, dout) if d.m is not None)
    cand = Candidate(mech, (din, dout), np.asarray(q, float), float(body_angle), lengths, grounds, pivots)
    return check(cand, poses, opts, zones, betas, quick)


# --------------------------------------------------------------------------
# Candidate generation

def prescribed_rotations(keyframes):
    """Input rotation from the first keyframe to each later one (rad), or
    None where the timing is free."""
    if not keyframes:
        return []
    t1 = keyframes[0].t if keyframes[0].timing == "absolute" else None
    out, prev = [0.0], 0.0
    for k in keyframes[1:]:
        if k.timing == "absolute" and t1 is not None:
            prev = k.t - t1
        elif k.timing == "relative" and prev is not None:
            prev = prev + k.t
        else:
            prev = None
        out.append(prev)
    return out


def _region(poses: Poses, zones):
    allowed = [p for z in zones if z.allow for p in z.polygon]
    if allowed:
        z = np.array(allowed)
        return z.real.min(), z.real.max(), z.imag.min(), z.imag.max()
    s = poses.scale()
    pad = 0.8 * s
    return (poses.P.real.min() - pad, poses.P.real.max() + pad,
            poses.P.imag.min() - pad, poses.P.imag.max() + pad)


def _ground_ok(p, zones):
    allowed = [z.polygon for z in zones if z.allow]
    return (not allowed or any(point_in_polygon(p, a) for a in allowed)) and \
        not any(point_in_polygon(p, z.polygon) for z in zones if not z.allow)


def ground_grid(poses: Poses, zones, n):
    x0, x1, y0, y1 = _region(poses, zones)
    xs, ys = np.linspace(x0, x1, n), np.linspace(y0, y1, n)
    return [p for p in (complex(x, y) for y in ys for x in xs) if _ground_ok(p, zones)]


def _tag(d: Dyad):
    """Which fixed pivot a dyad would satisfy: by its free choice, which can
    differ from the dyad itself once snapped onto a Burmester curve."""
    tag, choice = (d.source[0], d.source[1]) if d.source else (None, None)
    if d.kind == "RR":
        return ("pin", choice if tag in ("G", "timed") and choice is not None else d.G)
    if d.kind == "PR":
        return ("rail", choice if tag == "gamma" else d.angle)
    return None


def _dyad(poses, kind, choice, s=0.0):
    """Dyad from a free choice; with 4+ poses the choice is snapped onto
    what works first (see dyad.resolve)."""
    tag = {"RR": "G", "PR": "gamma", "RP": "phi"}[kind]
    return resolve(poses, Dyad(kind, source=(tag, choice, s)))


def generate(poses: Poses, opts: Options, zones=(), fixed=(), betas=None):
    """Dyads to pair up: (inputs, outputs), each a dict by dyad kind. Fixed
    pivots are tried first; the grid and direction sweeps are skipped when
    two pivots are fixed."""
    n = len(poses)
    offsets = (0.0,) if n >= 3 else (-0.5, 0.0, 0.5)
    fixed_pins = [p.pos for p in fixed if p.slider_angle is None]
    fixed_rails = [p.slider_angle for p in fixed if p.slider_angle is not None]
    free = len(fixed) < 2
    want = set(opts.families)
    use_pr = "slider_crank" in want
    use_rp = "inverted_slider" in want and free
    if n >= 4:
        # Only points of the center-point curve (4 poses) or the Burmester
        # points (5 poses) work, and only a few slider directions.
        if not free:
            grid = []
        elif n == 4:
            curves = burmester.curves(poses, burmester.default_box(poses, zones))
            grid = [g for g in burmester.sample_curve(curves, opts.curve_samples)
                    if _ground_ok(g, zones)]
        else:
            grid = [d.G for d in burmester.burmester_points(poses)]
        dirs = {k: burmester.slider_directions(poses, k) if free else [] for k in ("PR", "RP")}
    else:
        grid = ground_grid(poses, zones, opts.grid) if free else []
        sweep = list(np.linspace(0, math.pi, opts.directions, endpoint=False)) if free else []
        dirs = {"PR": sweep, "RP": sweep}

    def make(kind, choices):
        out = []
        for c in choices:
            for s in offsets:
                d = _dyad(poses, kind, c, s)
                if d is not None:
                    out.append(d)
        return out

    rr = make("RR", fixed_pins + grid)
    pr = make("PR", fixed_rails + dirs["PR"]) if use_pr else []
    rp = make("RP", dirs["RP"]) if use_rp else []
    outputs = {"RR": rr, "PR": pr, "RP": rp}

    if betas is not None:
        if n >= 3:
            d = rr_from_timing(poses, betas)
            inputs = {"RR": [d] if d is not None else []}
        else:
            ins = []
            for G in fixed_pins + grid:
                d = rr_from_timing(poses, betas, G)
                if d is not None:
                    ins.append(d)
            inputs = {"RR": ins}
    else:
        inputs = outputs
    return inputs, outputs


def _pairs(inputs, outputs, families, fixed=()):
    """All (input, output) dyad pairs that make a wanted family and use
    every fixed pivot."""
    need = [("pin", p.pos) if p.slider_angle is None else ("rail", p.slider_angle) for p in fixed]
    out = []
    for kin, kout in (("RR", "RR"), ("RR", "PR"), ("PR", "RR"), ("RR", "RP"), ("RP", "RR")):
        if _family_of((kin, kout)) not in families:
            continue
        for di in inputs.get(kin, []):
            for do in outputs.get(kout, []):
                if di is do or (di.G is not None and do.G is not None and abs(di.G - do.G) < 1e-9):
                    continue
                if need and not all(t in (_tag(di), _tag(do)) for t in need):
                    continue
                out.append((di, do))
    return out


def _distinct(cands, scale, limit):
    """Greedy pick of candidates that differ: skip one whose ground pivots
    are all close to an already picked candidate of the same kind."""
    picked = []
    tol = 0.06 * scale
    for c in cands:
        if any(p.family == c.family and p.input_name() == c.input_name()
               and len(p.pivots) == len(c.pivots)
               and all(abs(a - b) < tol for a, b in zip(p.pivots, c.pivots))
               for p in picked):
            continue
        picked.append(c)
        if len(picked) >= limit:
            break
    return picked


def _by_family(cands, scale, limit):
    """Best distinct candidates, taking turns between the mechanism types
    (and inputs) so the top of the list shows the best of each. Ranking all
    together would let one type crowd out the rest: a slotted lever with no
    offset, for example, always has a transmission angle near 90°."""
    groups = {}
    for c in sorted(cands, key=rank_key):
        groups.setdefault((c.family, c.input_name()), []).append(c)
    if not groups:
        return []
    share = max(limit // len(groups), 1)
    lists = [_distinct(g, scale, share) for g in groups.values()]
    out = []
    for k in range(max(map(len, lists))):
        out += [lst[k] for lst in sorted(lists, key=lambda lst: rank_key(lst[0])) if k < len(lst)]
    return out


def rank_key(c: Candidate):
    """Best first: high transmission angle, then compact proportions."""
    mu = c.mu_min if np.isfinite(c.mu_min) else math.radians(45)
    return -(math.degrees(mu) - 6 * math.log(c.ratio))


def solve_motion(keyframes, opts: Options | None = None, zones=(), fixed=(), should_stop=None):
    """Motion generation for the keyframes (2 to 5 exact poses).

    `should_stop()` is polled now and then; when it returns True the solve
    gives up and returns None (a newer solve has replaced it)."""
    opts = opts or Options()
    res = Result()
    n = len(keyframes)
    if n < 2:
        res.method = "Add at least 2 poses"
        return res
    if n > 5:
        res.method = f"{n} poses: more than 5 exact poses needs the optimizer (a later milestone)"
        return res
    if not all(k.exact for k in keyframes):
        res.notes.append("Tolerances are ignored: the exact solvers hit every pose exactly.")
    poses = Poses.of(keyframes)
    rot = prescribed_rotations(keyframes)
    betas = rot if all(r is not None for r in rot) else None
    if n >= 4 and any(r is not None for r in rot[1:]):
        res.notes.append(f"Timing is ignored: with {n} poses there is no exact solution with prescribed timing.")
        betas = None
    elif betas is None and any(r is not None for r in rot[1:]):
        res.notes.append("Timing is ignored: prescribe it for every pose, or for none.")
    if len(fixed) > 2:
        res.notes.append("Only the first two fixed pivots are used.")
        fixed = fixed[:2]
    if betas is not None:
        res.method = f"{n} exact poses with prescribed timing → " + (
            "unique input dyad" if n >= 3 else "input dyad for each ground pivot")
    else:
        res.method = f"{n} exact poses → " + {2: "closed-form dyads", 3: "dyad solve",
                                              4: "Burmester curves", 5: "Burmester points"}[n]
    if n >= 4:
        _burmester_info(res, poses, zones)
        if should_stop is not None and should_stop():
            return None

    inputs, outputs = generate(poses, opts, zones, fixed, betas)
    pairs = _pairs(inputs, outputs, set(opts.families), fixed)
    res.combinations = len(pairs)
    # Random order (fixed seed, so re-solves are stable) spreads a limited
    # budget evenly over the free choices.
    order = np.random.default_rng(0).permutation(len(pairs)) if len(pairs) > opts.budget else range(len(pairs))
    good, bad = [], []
    full = 0
    for n_done, i in enumerate(order):
        if should_stop is not None and n_done % 200 == 0 and should_stop():
            return None
        if full >= opts.budget:
            res.notes.append(f"Checked {full} of {res.combinations} combinations in full.")
            break
        c = evaluate(poses, *pairs[i], opts, zones, betas, quick=True)
        if c is None:
            continue
        res.evaluated += 1
        full += c.checked
        if c.valid:
            good.append(c)
        else:
            bad.append(c)
            res.reject_counts[c.reasons[0][0]] += 1
    scale = poses.scale()
    res.solutions = _by_family(good, scale, opts.max_results)
    # Keep the most promising rejects: fewest problems, then best rank.
    bad = [c for c in bad if c.checked]
    bad.sort(key=lambda c: (len(c.reasons), rank_key(c)))
    res.rejected = _distinct(bad, scale, 80)
    return res


def _burmester_info(res, poses, zones):
    """Curves, points and slider directions, for drawing and the status line."""
    n = len(poses)
    if n == 4:
        res.curves = [burmester.curves(poses, burmester.default_box(poses, zones))]
    else:
        box = burmester.default_box(poses, zones)
        res.curves = [burmester.curves(Poses(poses.P[list(ix)], poses.th[list(ix)]), box)
                      for ix in ((0, 1, 2, 3), (0, 1, 2, 4))]
        res.burmester_points = [d.G for d in burmester.burmester_points(poses)]
        k = len(res.burmester_points)
        res.method += f" ({k} found)"
        if k == 0:
            res.notes.append("These 5 poses have no real Burmester points, so no pin-jointed four-bar "
                             "hits them all exactly. Try moving a pose, or use 4 poses.")
    res.slider_dirs = {k: burmester.slider_directions(poses, k) for k in ("PR", "RP")}


def resolve_candidate(cand: Candidate, keyframes, opts: Options, zones=()):
    """The same design (same free choices) for edited poses, re-checked.
    None when it no longer exists."""
    poses = Poses.of(keyframes)
    rot = prescribed_rotations(keyframes)
    betas = rot if all(r is not None for r in rot) else None
    dyads = [resolve(poses, d, betas) for d in cand.dyads]
    if None in dyads:
        return None
    return evaluate(poses, dyads[0], dyads[1], opts, zones, betas)
