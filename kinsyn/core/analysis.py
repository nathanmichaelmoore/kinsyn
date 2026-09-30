"""Mechanism-independent analysis: input ranges, circuit tracing with branch
tracking, toggle (over-center) detection and summary metrics."""

import math
from dataclasses import dataclass, field

import numpy as np

from .mechanism import Frames, Mechanism

MU_LIMIT_DEFAULT = math.radians(40)


def feasible_intervals(mech: Mechanism, n=4096):
    """Input intervals over which the mechanism assembles.

    Returns (intervals, full_rotation). For a periodic input with full
    rotation this is ([(lo, lo + 2pi)], True). Interval ends are refined by
    bisection so they sit on the toggle (limit) positions."""
    lo, hi, periodic = mech.input_domain()
    q = np.linspace(lo, hi, n + 1)
    ok = mech.solve(q).ok
    if ok.all():
        return [(lo, hi)], periodic
    if not ok.any():
        return [], False

    def refine(good, bad):
        for _ in range(60):
            mid = 0.5 * (good + bad)
            if mech.solve(np.array([mid])).ok[0]:
                good = mid
            else:
                bad = mid
        return good

    runs = []
    i = 0
    while i <= n:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j < n and ok[j + 1]:
            j += 1
        left = q[i] if i == 0 else refine(q[i], q[i - 1])
        right = q[j] if j == n else refine(q[j], q[j + 1])
        runs.append([left, right, i == 0, j == n])
        i = j + 1
    if periodic and len(runs) > 1 and runs[0][2] and runs[-1][3]:
        first = runs.pop(0)
        runs[-1][1] = first[1] + (hi - lo)
    return [(r[0], r[1]) for r in runs], False


@dataclass
class Circuit:
    """One continuous motion cycle of the mechanism."""
    frames: Frames
    interval: tuple
    full_rotation: bool

    @property
    def q(self):
        return self.frames.q


def circuit_inputs(interval, full, n=720):
    lo, hi = interval
    if full:
        # Start a quarter turn in, away from the usual change-point at 0.
        return lo + 0.25 * (hi - lo) + np.arange(n) * (hi - lo) / n
    # Rocking input: mid -> hi -> lo -> mid. The mechanism passes to the
    # other assembly at each limit, so this traces one closed circuit.
    mid = 0.5 * (lo + hi)
    n1 = n // 4
    n2 = n - 2 * n1
    return np.concatenate([
        np.linspace(mid, hi, n1, endpoint=False),
        np.linspace(hi, lo, n2, endpoint=False),
        np.linspace(lo, mid, n1, endpoint=False),
    ])


def trace_circuit(mech: Mechanism, interval, full, n=720) -> Circuit:
    """Solve along the circuit, choosing between the two assemblies at each
    step by continuity (linear prediction from the previous two samples).
    This keeps a parallelogram a parallelogram through its change point and
    switches assembly at the limits of a rocking input, as the real linkage does."""
    q = circuit_inputs(interval, full, n)
    if not mech.has_branches:
        return Circuit(mech.solve(q), interval, full)
    fa = mech.solve(q, mech.branch)
    fb = mech.solve(q, -mech.branch)
    keys = [k for k in fa.points if not k.startswith("dir:")]
    Xa = np.stack([fa.points[k] for k in keys])
    Xb = np.stack([fb.points[k] for k in keys])
    take_b = np.zeros(len(q), bool)
    prev2, prev = None, Xa[:, 0]
    for i in range(1, len(q)):
        pred = prev if prev2 is None else 2 * prev - prev2
        da = np.nansum(np.abs(Xa[:, i] - pred))
        db = np.nansum(np.abs(Xb[:, i] - pred))
        take_b[i] = db < da
        cur = Xb[:, i] if take_b[i] else Xa[:, i]
        prev2, prev = prev, cur
    return Circuit(Frames.select(fa, fb, take_b), interval, full)


def mechanical_advantage(mech: Mechanism, circuit: Circuit):
    """|d input / d output| along the circuit: output torque (or force) per
    unit input torque (or force), ignoring friction. Infinite at a toggle."""
    out = circuit.frames.output
    if mech.output_kind == "angle":
        out = np.unwrap(out)
    q = circuit.q
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.abs(np.gradient(q) / np.gradient(out))


def find_toggles(mech: Mechanism, circuit: Circuit):
    """Where the input link and coupler are collinear: the output is at a
    dead point, i.e. the over-center (toggle) condition. Returns a list of
    (nearest circuit index, interpolated input value)."""
    keys = mech.toggle_links()
    if keys is None:
        return []
    p = circuit.frames.points
    q = circuit.q
    fixed, joint, far = (p[k] for k in keys)
    cross = ((np.conj(joint - fixed)) * (far - joint)).imag
    n = len(q)
    period = circuit.interval[1] - circuit.interval[0]
    found = []
    for i in range(n if circuit.full_rotation else n - 1):
        j = (i + 1) % n
        ci, cj = cross[i], cross[j]
        if not (np.isfinite(ci) and np.isfinite(cj)):
            continue
        if ci == 0 or (ci > 0) != (cj > 0) and cj != 0:
            qj = q[j] + (period if j < i else 0.0)
            t = 0.0 if ci == 0 else ci / (ci - cj)
            found.append((i if t < 0.5 else j, float(q[i] + t * (qj - q[i]))))
    return found


@dataclass
class Summary:
    classification: str
    notes: list
    intervals: list
    full_rotation: bool
    mu_min: float  # worst transmission quality min(mu, 180-mu), rad; NaN if n/a
    mu_range: tuple
    output_range: tuple
    output_rotates: bool
    time_ratio: float | None
    toggles: list = field(default_factory=list)  # (circuit index, input value)
    warnings: list = field(default_factory=list)
    over_center: float | None = None  # travel past the toggle to the range end


def summarize(mech: Mechanism, circuit: Circuit, intervals, full, mu_limit=MU_LIMIT_DEFAULT,
              operating=None):
    name, notes = mech.classify()
    f = circuit.frames
    warnings = []

    mu = f.mu
    if np.isfinite(mu).any():
        quality = np.minimum(mu, math.pi - mu)
        mu_min = float(np.nanmin(quality))
        mu_range = (float(np.nanmin(mu)), float(np.nanmax(mu)))
        if mu_min < mu_limit:
            warnings.append(f"transmission angle drops to {math.degrees(mu_min):.1f} deg "
                            f"(limit {math.degrees(mu_limit):.0f} deg)")
    else:
        mu_min, mu_range = float("nan"), (float("nan"), float("nan"))

    out = f.output
    if mech.output_kind == "angle":
        out = np.unwrap(out)
    out_range = (float(np.nanmin(out)), float(np.nanmax(out)))
    # The output rotates if one trip round the (closed) circuit winds it by 2pi.
    output_rotates = False
    if mech.output_kind == "angle":
        closed = np.unwrap(np.append(f.output, f.output[0]))
        output_rotates = abs(closed[-1] - closed[0]) > math.pi

    time_ratio = None
    if full and not output_rotates:
        n = len(out)
        fwd = (int(np.nanargmax(out)) - int(np.nanargmin(out))) % n
        if 0 < fwd < n:
            time_ratio = max(fwd, n - fwd) / min(fwd, n - fwd)

    # A rocking circuit crosses each toggle twice (out and back); keep one.
    toggles = []
    for i, qt in find_toggles(mech, circuit):
        if all(abs(qt - q) > 1e-6 * max(1.0, mech.scale()) for _, q in toggles):
            toggles.append((i, qt))
    lo, hi = circuit.interval
    if (operating or not full) and mech.input_kind == "angle":
        notes.append(f"input {'operates' if operating else 'rocks'} through "
                     f"{math.degrees(hi - lo):.1f} deg")

    over_center = None
    if operating:
        span = hi - lo
        inner = [q for _, q in toggles if lo + 1e-3 * span < q < hi - 1e-3 * span]
        if inner:
            # Over-center travel: from the toggle to the nearer end of the range
            # (where the stop sits).
            over_center = min(min(q - lo, hi - q) for q in inner)
            unit = "deg" if mech.input_kind == "angle" else "mm"
            val = math.degrees(over_center) if unit == "deg" else over_center
            notes.append(f"over-center: stop is {val:.2f} {unit} past the toggle")
        else:
            notes.append("no toggle inside the operating range (no over-center lock)")

    return Summary(name, notes, intervals, full, mu_min, mu_range, out_range,
                   output_rotates, time_ratio, toggles, warnings, over_center)


def operating_circuit_ok(mech: Mechanism, operating, intervals, full):
    """The operating range must lie inside one assemblable interval."""
    lo, hi = operating
    if hi <= lo:
        return False
    if full:
        return True
    shifts = (-2 * math.pi, 0.0, 2 * math.pi) if mech.input_domain()[2] else (0.0,)
    eps = 1e-9
    return any(a - eps <= lo + k and hi + k <= b + eps for a, b in intervals for k in shifts)


def analyze(mech: Mechanism, circuit_index=0, n=720, operating=None, mu_limit=MU_LIMIT_DEFAULT):
    """Convenience: intervals + chosen circuit + summary. Returns
    (intervals, full, circuit or None, summary or None).

    `operating` = (lo, hi) restricts the input to a working range (e.g. a
    toggle clamp from open to its stop); the circuit then rocks over it."""
    intervals, full = feasible_intervals(mech)
    if not intervals:
        return intervals, full, None, None
    if operating is not None:
        if not operating_circuit_ok(mech, operating, intervals, full):
            return intervals, full, None, None
        circuit = trace_circuit(mech, tuple(operating), False, n)
        return intervals, full, circuit, summarize(mech, circuit, intervals, full, mu_limit, operating)
    circuit_index = min(circuit_index, len(intervals) - 1)
    circuit = trace_circuit(mech, intervals[circuit_index], full, n)
    return intervals, full, circuit, summarize(mech, circuit, intervals, full, mu_limit)
