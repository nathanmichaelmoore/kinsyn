import math

import numpy as np
import pytest

from kinsyn.core.families import FourBar, InvertedSliderCrank, SliderCrank
from kinsyn.core.target import FixedPivot
from kinsyn.synthesis import burmester as bm
from kinsyn.synthesis.dyad import Poses, rr_from_ground
from kinsyn.synthesis.motion import Options, resolve_candidate, solve_motion

from test_motion import FB, poses_of, reproduces

Q4 = [40, 80, 120, 170]
Q5 = [40, 70, 100, 130, 170]


def test_center_point_curve_passes_through_the_real_pivots():
    p4 = Poses.of(poses_of(FB, np.radians(Q4)))
    c = bm.curves(p4)
    for G in (FB.A0, FB.B0):
        assert min(np.abs(line - G).min() for line in c.center) < 1.0
        # The polyline is a sampling; the curve itself goes exactly through.
        assert bm.project_to_curve(p4, G + 0.3 + 0.2j) == pytest.approx(G, abs=0.5)
        assert rr_from_ground(p4, G) is not None


def test_every_curve_point_is_a_working_ground_pivot():
    p4 = Poses.of(poses_of(FB, np.radians(Q4)))
    pts = bm.sample_curve(bm.curves(p4), 40)
    assert len(pts) >= 30
    for G in pts:
        G = bm.project_to_curve(p4, G)
        d = rr_from_ground(p4, G)
        assert d is not None
        r = np.abs(p4.world(d.m) - G)
        assert np.ptp(r) < 1e-6 * max(p4.scale(), r.max())
        # Its moving pivot is on the circle-point curve.
    assert rr_from_ground(p4, 50 + 300j) is None  # off the curve: no dyad


def test_burmester_points_recover_the_pivots():
    p5 = Poses.of(poses_of(FB, np.radians(Q5)))
    pts = [d.G for d in bm.burmester_points(p5)]
    assert any(abs(g - FB.A0) < 1e-6 for g in pts)
    assert any(abs(g - FB.B0) < 1e-6 for g in pts)
    assert len(pts) in (2, 4)


def test_slider_directions_are_ball_point_roots():
    sc = SliderCrank(A0=10 + 5j, a=35, b=110, gamma=math.radians(15), e=12, P=50 + 30j)
    p4 = Poses.of(poses_of(sc, np.radians(Q4)))
    assert any(abs(r - sc.gamma) < 1e-9 for r in bm.slider_directions(p4, "PR"))
    inv = InvertedSliderCrank(A0=0j, a=40, B0=110 + 20j, e=8, P=-25 + 10j)
    p4 = Poses.of(poses_of(inv, np.radians(Q4)))
    assert any(abs(r) < 1e-9 or abs(r - math.pi) < 1e-9 for r in bm.slider_directions(p4, "RP"))


def test_four_pose_designs_reproduce_every_pose():
    kfs = poses_of(FB, np.radians(Q4))
    res = solve_motion(kfs, Options(budget=1500))
    assert res.method.startswith("4 exact poses") and res.curves
    assert res.solutions
    for c in res.solutions:
        assert c.valid and reproduces(c, kfs)


def test_five_poses_give_back_the_original_linkage():
    kfs = poses_of(FB, np.radians(Q5))
    res = solve_motion(kfs, Options(mu_min=0))
    assert "2 found" in res.method or "4 found" in res.method
    c = next(c for c in res.solutions if c.mech.A0 == pytest.approx(0j, abs=1e-6))
    assert (c.mech.a, c.mech.b, c.mech.c) == pytest.approx((40, 120, 80))
    assert reproduces(c, kfs)


def test_fixed_pivot_snaps_to_the_nearest_burmester_point():
    kfs = poses_of(FB, np.radians(Q5))
    res = solve_motion(kfs, Options(mu_min=0), fixed=[FixedPivot(2 + 1j), FixedPivot(98 - 2j)])
    grounds = {tuple(np.round(c.grounds, 6)) for c in res.solutions}
    assert (0j, 100 + 0j) in grounds or (100 + 0j, 0j) in grounds


def test_tracking_a_four_pose_design():
    kfs = poses_of(FB, np.radians(Q4))
    res = solve_motion(kfs, Options(budget=800))
    c = res.solutions[0]
    kfs[2].pos += 0.8 - 0.4j
    c2 = resolve_candidate(c, kfs, Options(mu_min=0))
    assert c2 is not None and reproduces(c2, kfs)
