import math

import numpy as np
import pytest

from kinsyn.core.families import FourBar
from kinsyn.core.project import Project, load_project, save_project
from kinsyn.core.snap import nice_step, snap_point
from kinsyn.core.target import (Body, Curve, FixedPivot, Keyframe, Target, Zone, catmull_rom,
                                pose_inverse, pose_transform, resample_even)


def poses(n, **kw):
    return Target(keyframes=[Keyframe(pos=complex(20 * i, 5 * i), angle=0.2 * i, **kw) for i in range(n)])


def test_pose_transform_roundtrip():
    pts = np.array([1 + 2j, -3 + 0.5j])
    w = pose_transform(pts, 10 + 5j, 0.7)
    assert np.allclose(pose_inverse(w, 10 + 5j, 0.7), pts)
    assert np.allclose(abs(w[0] - w[1]), abs(pts[0] - pts[1]))


def test_spline_passes_through_points():
    pts = [0j, 10 + 5j, 20 - 3j, 35 + 0j]
    dense = catmull_rom(pts, closed=False, per_segment=10)
    for p in pts:
        assert np.min(np.abs(dense - p)) < 1e-9
    closed = catmull_rom(pts, closed=True, per_segment=10)
    assert closed[0] == pytest.approx(closed[-1])


def test_resample_even_spacing():
    poly = np.array([0j, 10 + 0j, 10 + 10j])
    r = resample_even(poly, 5)
    assert np.allclose(np.abs(np.diff(r)), 5.0)
    assert r[0] == 0 and r[-1] == pytest.approx(10 + 10j)


@pytest.mark.parametrize("n, fragment", [
    (1, "at least 2"), (2, "closed-form"), (3, "dyad solve"), (4, "Burmester curves"),
    (5, "Burmester points"), (7, "over-constrained"),
])
def test_solver_hint_exact(n, fragment):
    assert fragment in poses(n).solver_hint()


def test_solver_hint_tolerance_and_timing():
    t = poses(4)
    t.keyframes[2].tol = 1.0
    assert "optimizer" in t.solver_hint()
    t = poses(4)
    t.keyframes[1].timing = "absolute"
    assert "prescribed timing" in t.solver_hint()
    assert "dyad" in poses(3).solver_hint()


def test_warnings():
    t = poses(3)
    t.keyframes.append(Keyframe(pos=t.keyframes[1].pos, angle=t.keyframes[1].angle))
    assert any("nearly identical" in m for _, m in t.warnings())
    t = poses(3)
    t.keyframes[1].timing, t.keyframes[1].t = "absolute", 1.0
    t.keyframes[2].timing, t.keyframes[2].t = "absolute", 0.5
    assert any("timed before" in m for _, m in t.warnings())


def test_target_and_project_roundtrip(tmp_path):
    t = poses(3)
    t.body = Body([[0j, 10 + 0j, 10 + 5j]])
    t.curves.append(Curve([0j, 5 + 5j, 10 + 0j], closed=True))
    t.zones.append(Zone([0j, 10 + 0j, 10 + 10j], allow=False))
    t.pivots.append(FixedPivot(3 + 4j, slider_angle=0.5))
    assert Target.from_dict(t.to_dict()) == t
    proj = Project(target=t, mechanism=FourBar(), operating_range=(0.1, 0.9), units="in")
    save_project(proj, tmp_path / "p.kinsyn")
    assert load_project(tmp_path / "p.kinsyn") == proj


def test_nice_step():
    assert nice_step(7, "mm") == 5
    assert nice_step(0.3, "mm") == pytest.approx(0.2)
    assert nice_step(25.4 / 7, "in") == pytest.approx(25.4 / 8)
    assert nice_step(60, "in") == pytest.approx(50.8)


def test_snap_priorities():
    pts = [10 + 10j, 50 + 0j]
    # Object snap beats everything.
    assert snap_point(10.4 + 9.7j, tol=1, points=pts, grid_step=5).point == 10 + 10j
    # Alignment on x, grid on y.
    r = snap_point(49.6 + 22.3j, tol=1, points=pts, grid_step=5)
    assert r.point == 50 + 20j and r.kind == "align"
    # Plain grid.
    assert snap_point(31.2 + 17.6j, tol=1, points=pts, grid_step=5).point == 30 + 20j
    # Angle snap from a reference point.
    r = snap_point(10 + 1j, tol=0.1, ref=0j, angle_step=math.radians(15))
    assert abs(r.point.imag) < 1e-9 and r.kind == "angle"


def test_simplify_freehand():
    from kinsyn.core.target import simplify
    t = np.linspace(0, np.pi, 400)
    noisy = 50 * np.exp(1j * t) + np.random.default_rng(0).normal(0, 0.2, 400)
    s = simplify(noisy, tol=1.0)
    assert 5 <= len(s) <= 30
    dense = catmull_rom(s, closed=False, per_segment=20)
    # The spline through the simplified points stays close to the stroke.
    assert np.max(np.min(np.abs(dense[:, None] - noisy[None, ::8]), axis=0)) < 2.0


def test_point_in_polygon():
    from kinsyn.core.target import point_in_polygon
    sq = [0j, 10 + 0j, 10 + 10j, 10j]
    assert point_in_polygon(5 + 5j, sq) and not point_in_polygon(15 + 5j, sq)
