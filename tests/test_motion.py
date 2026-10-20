import math

import numpy as np
import pytest

from kinsyn.core.families import FourBar, InvertedSliderCrank, SliderCrank
from kinsyn.core.target import FixedPivot, Keyframe, Zone
from kinsyn.synthesis.dyad import Poses, pr_from_direction, rp_from_direction, rr_from_ground, rr_from_timing
from kinsyn.synthesis.motion import Options, build, evaluate, resolve_candidate, solve_motion

FB = FourBar(A0=0j, B0=100 + 0j, a=40, b=120, c=80, P=60 + 40j, branch=1)


def poses_of(mech, q, branch=None, timed=False):
    """Keyframes the coupler of `mech` passes through at inputs q."""
    f = mech.solve(np.asarray(q, float), branch)
    ang = mech.coupler_angle(f)
    kfs = [Keyframe(pos=complex(p), angle=float(a)) for p, a in zip(f.points["P"], ang)]
    if timed:
        for k, t in zip(kfs, q):
            k.timing, k.t = "absolute", float(t)
    return kfs


def reproduces(c, kfs):
    """Independent round trip: solve the candidate at its pose inputs."""
    f = c.mech.solve(c.q)
    ang = c.mech.coupler_angle(f) + c.body_angle
    for i, k in enumerate(kfs):
        if abs(f.points["P"][i] - k.pos) > 1e-6 or abs(math.remainder(ang[i] - k.angle, 2 * math.pi)) > 1e-8:
            return False
    return True


def test_rr_dyad_keeps_constant_distance():
    kfs = poses_of(FB, np.radians([60, 100, 150]))
    poses = Poses.of(kfs)
    d = rr_from_ground(poses, 30 - 40j)
    M = poses.world(d.m)
    assert np.allclose(np.abs(M - d.G), abs(M[0] - d.G))
    # Two poses leave a line of moving pivots; each still works.
    p2 = Poses.of(kfs[:2])
    for s in (-0.5, 0.0, 0.5):
        M = p2.world(rr_from_ground(p2, 30 - 40j, s).m)
        assert abs(M[0] - (30 - 40j)) == pytest.approx(abs(M[1] - (30 - 40j)))


def test_pr_dyad_points_are_collinear():
    poses = Poses.of(poses_of(FB, np.radians([60, 100, 150])))
    d = pr_from_direction(poses, math.radians(25))
    M = poses.world(d.m)
    assert np.allclose(((M - M[0]) * np.exp(-1j * d.angle)).imag, 0, atol=1e-9)


def test_fixed_pivots_recover_the_original_fourbar():
    kfs = poses_of(FB, np.radians([60, 100, 150]))
    res = solve_motion(kfs, fixed=[FixedPivot(0j), FixedPivot(100 + 0j)])
    c = next(c for c in res.solutions if c.mech.A0 == 0j)
    assert (c.mech.a, c.mech.b, c.mech.c) == pytest.approx((40, 120, 80))
    assert c.mech.P == pytest.approx(60 + 40j)
    assert c.mech.branch == 1
    assert c.classification == "Crank-rocker"
    assert c.error < 1e-9


@pytest.mark.parametrize("driver", ["crank", "slider"])
def test_slider_crank_round_trip(driver):
    sc = SliderCrank(A0=10 + 5j, a=35, b=110, gamma=math.radians(15), e=12, P=50 + 30j, driver=driver)
    q = np.radians([40, 90, 140]) if driver == "crank" else np.array([90.0, 110.0, 130.0])
    kfs = poses_of(sc, q)
    poses = Poses.of(kfs)
    crank = rr_from_ground(poses, sc.A0)
    rail = pr_from_direction(poses, sc.gamma)
    pair = (crank, rail) if driver == "crank" else (rail, crank)
    c = evaluate(poses, *pair, Options(mu_min=0))
    assert reproduces(c, kfs)
    assert (c.mech.a, c.mech.b, c.mech.e) == pytest.approx((35, 110, 12))
    assert c.mech.driver == driver


def test_inverted_slider_round_trip():
    inv = InvertedSliderCrank(A0=0j, a=40, B0=110 + 20j, e=8, P=-25 + 10j)
    kfs = poses_of(inv, np.radians([30, 80, 130]))
    poses = Poses.of(kfs)
    crank = rr_from_ground(poses, inv.A0)
    # The body frame is the slide frame, so the slide runs along body x.
    swivel = rp_from_direction(poses, 0.0)
    assert swivel.G == pytest.approx(inv.B0)
    c = evaluate(poses, crank, swivel, Options(mu_min=0))
    assert reproduces(c, kfs)
    assert (c.mech.a, c.mech.e) == pytest.approx((40, 8))


def test_every_solution_reproduces_the_poses():
    kfs = poses_of(FB, np.radians([60, 100, 150]))
    res = solve_motion(kfs, Options(budget=1500))
    assert res.solutions
    assert {c.family for c in res.solutions} >= {"fourbar", "slider_crank", "inverted_slider"}
    for c in res.solutions:
        assert c.valid and reproduces(c, kfs)
        assert c.mu_min >= math.radians(40)
        assert c.ratio <= 10
    for c in res.rejected:
        assert c.reasons


def test_branch_defect_is_rejected():
    # Poses 1 and 2 on one assembly, pose 3 on the other.
    kfs = poses_of(FB, np.radians([60, 100]), 1) + poses_of(FB, np.radians([150]), -1)
    res = solve_motion(kfs, Options(mu_min=0), fixed=[FixedPivot(0j), FixedPivot(100 + 0j)])
    c = next(c for c in res.rejected if c.mech.A0 == 0j)
    assert c.reasons[0][0] == "branch defect"


def test_order_defect_is_rejected():
    # A rocking (triple-rocker) input visited out of order: 1, 3, 2.
    tr = FourBar(A0=0j, B0=100 + 0j, a=75, b=80, c=90, P=30 + 20j)
    kfs = poses_of(tr, np.radians([20, 60, 40]))
    res = solve_motion(kfs, Options(mu_min=0), fixed=[FixedPivot(0j), FixedPivot(100 + 0j)])
    c = next(c for c in res.solutions + res.rejected if c.mech.A0 == 0j)
    assert not c.full_rotation
    assert c.reasons[0][0] == "order defect"


def test_prescribed_timing_gives_the_unique_input_dyad():
    q = np.radians([60, 100, 150])
    kfs = poses_of(FB, q, timed=True)
    d = rr_from_timing(Poses.of(kfs), list(q - q[0]))
    assert d.G == pytest.approx(0j, abs=1e-9)
    res = solve_motion(kfs, Options(budget=800))
    assert res.solutions
    for c in res.solutions:
        assert c.mech.A0 == pytest.approx(0j, abs=1e-6)
        assert np.allclose(np.mod(c.q - c.q[0] - (q - q[0]) + 1, 2 * math.pi) - 1, 0, atol=1e-9)


def test_two_poses():
    kfs = poses_of(FB, np.radians([60, 120]))
    res = solve_motion(kfs, Options(budget=800))
    assert res.solutions
    assert all(reproduces(c, kfs) for c in res.solutions)


def test_zones_and_full_rotation_option():
    kfs = poses_of(FB, np.radians([60, 100, 150]))
    zone = Zone([-40 - 60j, 160 - 60j, 160 + 10j, -40 + 10j])
    res = solve_motion(kfs, Options(input_motion="full", budget=1500), zones=[zone])
    assert res.solutions
    for c in res.solutions:
        assert c.full_rotation
        assert all(-40 <= g.real <= 160 and -60 <= g.imag <= 10 for g in c.grounds)


def test_tracking_a_design_while_a_pose_moves():
    kfs = poses_of(FB, np.radians([60, 100, 150]))
    res = solve_motion(kfs, fixed=[FixedPivot(0j), FixedPivot(100 + 0j)])
    c = res.solutions[0]
    kfs[1].pos += 1.5 + 0.5j
    c2 = resolve_candidate(c, kfs, Options())
    assert c2 is not None and reproduces(c2, kfs)
    assert c2.mech.A0 == c.mech.A0 and c2.mech.a != pytest.approx(c.mech.a)


def test_build_rejects_rod_passing_through_swivel():
    kfs = poses_of(FB, np.radians([60, 100, 150]))
    poses = Poses.of(kfs)
    crank = rr_from_ground(poses, 0j)
    # A swivel placed right on the path of the crank pin.
    swivel = rp_from_direction(poses, math.radians(90))
    built = build(poses, crank, swivel)
    if built is not None:
        mech = built[0]
        A = poses.world(crank.m)
        u = np.exp(1j * (math.radians(90) + poses.th))
        ahead = ((mech.B0 - A) * np.conj(u)).real
        assert (ahead > 0).all() or (ahead < 0).all()
