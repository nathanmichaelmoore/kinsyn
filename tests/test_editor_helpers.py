import math

import pytest

from kinsyn.core.target import Keyframe
from kinsyn.gui.target_panel import parse_table
from kinsyn.gui.timeline import display_times, resolved_times
from kinsyn.gui.tools import parse_coords


def test_parse_coords():
    assert parse_coords("10, 20", "mm") == (10 + 20j, None)
    pos, ang = parse_coords("1in, 2in, 90", "mm")
    assert pos == pytest.approx(25.4 + 50.8j) and ang == pytest.approx(math.pi / 2)
    pos, ang = parse_coords("@5, -5, 10", "mm", (100 + 0j, 0.5))
    assert pos == 105 - 5j and ang == pytest.approx(0.5 + math.radians(10))
    with pytest.raises(ValueError):
        parse_coords("@1, 1", "mm", None)
    with pytest.raises(ValueError):
        parse_coords("12", "mm")


def test_parse_table_formats():
    rows = parse_table("x\ty\n1\t2\n3,4,90\n5 6\n", "in")
    assert [r[0] for r in rows] == pytest.approx([25.4 + 50.8j, 76.2 + 101.6j, 127 + 152.4j])
    assert rows[1][1] == pytest.approx(math.pi / 2)
    with pytest.raises(ValueError):
        parse_table("1\t2\nfoo\tbar\n", "mm")


def test_timeline_times():
    ks = [Keyframe(0j), Keyframe(1j, timing="absolute", t=1.0), Keyframe(2j, timing="relative", t=0.5),
          Keyframe(3j), Keyframe(4j, timing="absolute", t=3.0)]
    assert resolved_times(ks) == [None, 1.0, 1.5, None, 3.0]
    shown = display_times(ks)
    assert shown[1:3] == [1.0, 1.5] and shown[4] == 3.0
    assert 1.5 < shown[3] < 3.0 and shown[0] < 1.0
    free = display_times([Keyframe(0j), Keyframe(1j)])
    assert free == pytest.approx([math.pi / 2, 3 * math.pi / 2])
