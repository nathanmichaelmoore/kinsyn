import math

import numpy as np
import pytest

from kinsyn.core.analysis import analyze, feasible_intervals
from kinsyn.core.families import (EllipticalTrammel, FourBar, InvertedSliderCrank, ScotchYoke,
                                  SliderCrank, circle_intersect, classify_fourbar)
from kinsyn.core.mechanism import Mechanism

ALL_DEFAULTS = [FourBar(), SliderCrank(), SliderCrank(e=20, driver="slider"),
                InvertedSliderCrank(), InvertedSliderCrank(e=10),
                InvertedSliderCrank(B0=120 - 30j, driver="stroke"), ScotchYoke(), EllipticalTrammel()]


def circuit_frames(m):
    _, _, circuit, _ = analyze(m)
    assert circuit is not None
    f = circuit.frames
    assert f.ok.all()
    return f


def test_circle_intersect_sides():
    left = circle_intersect(0j, 5.0, 8 + 0j, 5.0, 1)
    right = circle_intersect(0j, 5.0, 8 + 0j, 5.0, -1)
    assert left == pytest.approx(4 + 3j)
    assert right == pytest.approx(4 - 3j)
    assert np.isnan(circle_intersect(0j, 1.0, 10 + 0j, 1.0, 1))


@pytest.mark.parametrize("branch", [1, -1])
def test_fourbar_constraints(branch):
    m = FourBar(A0=5 + 3j, B0=90 + 20j, a=30, b=95, c=70, P=40 + 25j, branch=branch)
    p = circuit_frames(m).points
    assert np.allclose(abs(p["A"] - m.A0), m.a)
    assert np.allclose(abs(p["B"] - p["A"]), m.b)
    assert np.allclose(abs(p["B"] - m.B0), m.c)
    # The coupler point is rigidly attached to AB.
    assert np.allclose(abs(p["P"] - p["A"]), abs(m.P))
    assert np.allclose(abs(p["P"] - p["B"]), abs(m.P - m.b))


@pytest.mark.parametrize("driver", ["crank", "slider"])
def test_slider_crank_constraints(driver):
    m = SliderCrank(A0=2 - 1j, a=30, b=100, gamma=0.3, e=15, driver=driver)
    p = circuit_frames(m).points
    ug = np.exp(1j * m.gamma)
    assert np.allclose(((p["B"] - m.A0) / ug).imag, m.e)
    assert np.allclose(abs(p["A"] - m.A0), m.a)
    assert np.allclose(abs(p["B"] - p["A"]), m.b)


@pytest.mark.parametrize("driver, e", [("crank", 0.0), ("crank", 12.0), ("stroke", 8.0)])
def test_inverted_constraints(driver, e):
    m = InvertedSliderCrank(a=40, B0=110 - 20j, e=e, driver=driver)
    f = circuit_frames(m)
    p = f.points
    u = p["dir:rod"]
    # B0 sits at signed perpendicular distance e from the slide line through A.
    assert np.allclose(((m.B0 - p["A"]) * np.conj(u)).imag, e)
    assert np.allclose(abs(p["A"] - m.A0), m.a)
    if driver == "stroke":
        assert np.allclose(abs(p["F"] - p["A"]), f.q)


def test_trammel_and_yoke():
    t = EllipticalTrammel(O=3 + 4j, gamma1=0.2, gamma2=1.5, b=70)
    p = circuit_frames(t).points
    for key, g in (("B1", t.gamma1), ("B2", t.gamma2)):
        assert np.allclose(((p[key] - t.O) * np.exp(-1j * g)).imag, 0, atol=1e-9)
    assert np.allclose(abs(p["B2"] - p["B1"]), t.b)
    y = ScotchYoke(a=40)
    f = circuit_frames(y)
    assert np.allclose(f.output, 40 * np.cos(f.q))


@pytest.mark.parametrize("lengths, name", [
    ((100, 30, 110, 70), "Crank-rocker"),
    ((30, 70, 80, 90), "Double-crank (drag link)"),
    ((100, 80, 30, 90), "Double-rocker (Grashof)"),
    ((100, 70, 60, 80), "Triple-rocker (non-Grashof)"),
    ((60, 40, 90, 70), "Change point (Grashof boundary)"),
    ((100, 90, 70, 30), "Rocker-crank"),
])
def test_grashof_classes(lengths, name):
    assert classify_fourbar(*lengths)[0] == name


def test_rotatability_matches_grashof():
    crank = FourBar(B0=100, a=30, b=110, c=70)
    assert feasible_intervals(crank)[1] is True
    rocker = FourBar(B0=100, a=70, b=60, c=80)
    intervals, full = feasible_intervals(rocker)
    assert not full and len(intervals) == 1
    # Slider-crank: rotates iff b >= a + |e|.
    assert feasible_intervals(SliderCrank(a=30, b=100, e=70))[1] is True
    assert feasible_intervals(SliderCrank(a=30, b=100, e=71))[1] is False


def test_rocking_limits_are_toggles():
    m = FourBar(B0=100, a=70, b=60, c=80)
    (lo, hi), = feasible_intervals(m)[0]
    for q in (lo, hi):
        p = m.solve(np.array([q])).points
        d = abs(p["A"][0] - m.B0)
        assert min(abs(d - (m.b + m.c)), abs(d - abs(m.b - m.c))) < 1e-6


@pytest.mark.parametrize("m", ALL_DEFAULTS, ids=lambda m: m.kind + "-" + getattr(m, "driver", ""))
def test_circuit_is_continuous(m):
    """Branch tracking must never jump between assemblies."""
    f = circuit_frames(m)
    X = np.stack([v for k, v in f.points.items() if not k.startswith("dir:")])
    steps = np.abs(np.diff(np.concatenate([X, X[:, :1]], axis=1), axis=1)).max()
    assert steps < 0.25 * m.scale()


def test_parallelogram_stays_parallelogram():
    m = FourBar(B0=100, a=40, b=100, c=40, P=50 + 30j, branch=1)
    p = circuit_frames(m).points
    assert np.allclose(p["B"] - p["A"], m.B0 - m.A0, atol=1e-6)


def test_toggle_press_over_center():
    m = SliderCrank(a=30, b=90)
    _, _, _, s = analyze(m, operating=(math.radians(-70), math.radians(4)))
    assert s.over_center == pytest.approx(math.radians(4), abs=1e-6)
    _, _, _, s = analyze(m, operating=(math.radians(-70), math.radians(-4)))
    assert s.over_center is None and any("no over-center" in n for n in s.notes)


@pytest.mark.parametrize("m", ALL_DEFAULTS, ids=lambda m: m.kind)
def test_serialization_roundtrip(m):
    assert Mechanism.from_dict(m.to_dict()) == m
