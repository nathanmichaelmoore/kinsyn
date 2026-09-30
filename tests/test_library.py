import numpy as np
import pytest

from kinsyn.core.analysis import analyze
from kinsyn.library.catalog import Entry, load_all, save_user_entry

ENTRIES = load_all()


def test_library_loads():
    assert len(ENTRIES) >= 18
    assert len({e.id for e in ENTRIES}) == len(ENTRIES)


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.id)
def test_entry_analyzes_and_classifies(entry):
    _, _, circuit, summary = analyze(entry.mechanism, operating=entry.operating_range)
    assert circuit is not None and circuit.frames.ok.all()
    if entry.expected_class:
        assert summary.classification == entry.expected_class
    if "over-center" in entry.tags:
        assert summary.over_center is not None and 0 < np.degrees(summary.over_center) < 10


def test_search():
    hits = [e.id for e in ENTRIES if e.matches("over-center clamp")]
    assert hits == ["toggle_clamp"]


def test_user_entries_roundtrip(tmp_path):
    base = ENTRIES[0]
    mine = Entry(id="my_design", name="Mine", group="My designs", description="test",
                 mechanism=base.mechanism.copy(a=33.0), builtin=False)
    save_user_entry(mine, tmp_path)
    loaded = [e for e in load_all(tmp_path) if not e.builtin]
    assert len(loaded) == 1 and loaded[0].mechanism == mine.mechanism
