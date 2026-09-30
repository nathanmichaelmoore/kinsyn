import math

import pytest

from kinsyn.core.units import format_angle, format_length, parse_angle, parse_length


@pytest.mark.parametrize("text, unit, mm", [
    ("10", "mm", 10.0),
    ("10", "in", 254.0),
    ("2.5in", "mm", 63.5),
    ("1/4\"", "mm", 6.35),
    ("1 1/4 in", "mm", 31.75),
    ("2*25.4", "mm", 50.8),
    ("(2+3)mm", "in", 5.0),
    ("1in + 3mm", "mm", 28.4),
    ("3 cm", "mm", 30.0),
    ("0.1 m", "in", 100.0),
    ("-4.5", "cm", -45.0),
])
def test_parse_length(text, unit, mm):
    assert parse_length(text, unit) == pytest.approx(mm)


@pytest.mark.parametrize("bad", ["", "abc", "1/0", "__import__('os')", "2 +"])
def test_parse_length_rejects(bad):
    with pytest.raises(ValueError):
        parse_length(bad)


def test_parse_angle():
    assert parse_angle("90") == pytest.approx(math.pi / 2)
    assert parse_angle("pi/2 rad") == pytest.approx(math.pi / 2)
    assert parse_angle("45°") == pytest.approx(math.pi / 4)


def test_format_roundtrip():
    assert format_length(25.4, "in") == "1"
    assert format_length(12.5, "mm") == "12.5"
    assert format_angle(math.pi) == "180"
