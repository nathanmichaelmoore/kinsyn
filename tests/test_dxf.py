import numpy as np
import pytest

ezdxf = pytest.importorskip("ezdxf")

from kinsyn.core.dxf import distance_to_polyline, load_dxf  # noqa: E402


def make_dxf(path, insunits):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "frame"})
    msp.add_line((5, -5), (5, 5), dxfattribs={"layer": "frame"})
    msp.add_circle((20, 0), 3, dxfattribs={"layer": "holes"})
    msp.add_arc((0, 20), 5, 0, 90)
    msp.add_lwpolyline([(30, 0), (40, 0), (40, 10), (30, 10)], close=True, dxfattribs={"layer": "part"})
    blk = doc.blocks.new("PIN")
    blk.add_circle((0, 0), 1)
    msp.add_blockref("PIN", (50, 50))
    msp.add_text("label")
    doc.saveas(path)


def test_load_dxf_mm(tmp_path):
    f = tmp_path / "a.dxf"
    make_dxf(f, 4)
    g = load_dxf(f)
    assert g.units == "mm" and g.unit_known and g.mm_per_unit == 1.0
    kinds = sorted(e.kind for e in g.entities)
    assert kinds == ["ARC", "CIRCLE", "CIRCLE", "LINE", "LINE", "LWPOLYLINE"]
    assert g.skipped.get("TEXT") == 1
    assert set(g.layers) >= {"frame", "holes", "part"}
    # Line endpoints, midpoint, circle centre, polyline vertex, line crossing.
    for p in (0j, 10 + 0j, 5 + 0j, 20 + 0j, 40 + 10j, 50 + 50j):
        assert np.min(np.abs(g.snaps - p)) < 1e-6
    circle = next(e for e in g.entities if e.kind == "CIRCLE" and e.layer == "holes")
    assert circle.closed and np.allclose(np.abs(circle.points - 20), 3, atol=0.06)


def test_load_dxf_inches_and_override(tmp_path):
    f = tmp_path / "b.dxf"
    make_dxf(f, 1)
    g = load_dxf(f)
    line = next(e for e in g.entities if e.kind == "LINE")
    assert abs(line.points[-1] - line.points[0]) == pytest.approx(254.0)
    g2 = load_dxf(f, units_override=1.0)
    line2 = next(e for e in g2.entities if e.kind == "LINE")
    assert abs(line2.points[-1] - line2.points[0]) == pytest.approx(10.0)


def test_distance_to_polyline():
    pts = np.array([0j, 10 + 0j, 10 + 10j])
    assert distance_to_polyline(5 + 3j, pts) == pytest.approx(3)
    assert distance_to_polyline(12 + 5j, pts) == pytest.approx(2)
