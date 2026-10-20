"""Headless checks of the synthesis panel: solving, sorting, picking a
design and following it while the target is edited."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6 import QtWidgets

from kinsyn.core.families import FourBar
from kinsyn.core.target import Keyframe
from kinsyn.gui.document import TargetDocument
from kinsyn.gui.synthesis_panel import SynthesisPanel


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait(app, cond, secs=20):
    t0 = time.time()
    while not cond() and time.time() - t0 < secs:
        app.processEvents()
        time.sleep(0.005)
    return cond()


def test_panel_solves_sorts_and_tracks(app):
    doc = TargetDocument()
    panel = SynthesisPanel(doc, np.radians(40))
    picked = []
    panel.designSelected.connect(lambda c, new: picked.append((c, new)))
    fb = FourBar(A0=0j, B0=100 + 0j, a=40, b=120, c=80, P=60 + 40j)
    f = fb.solve(np.radians([60, 100, 150]))
    ang = fb.coupler_angle(f)
    doc.edit("poses", lambda t: t.keyframes.extend(Keyframe(complex(p), float(a))
                                                    for p, a in zip(f.points["P"], ang)))
    panel.solve()
    assert wait(app, lambda: panel.result is not None and panel.result.evaluated > 0)
    n = panel.table.rowCount()
    assert n == len(panel.result.solutions) > 0

    # Sorting by every column (this once crashed inside Qt's own sort).
    for col in range(6):
        panel._on_header(col)
        panel._on_header(col)
    panel._on_header(4)  # ratio, ascending
    ratios = [c.ratio for c in panel.rows]
    assert ratios == sorted(ratios)

    panel.table.selectRow(0)
    assert picked and picked[-1] == (panel.rows[0], True)
    first = picked[-1][0]

    # Moving a pose re-solves the same design straight away.
    doc.edit("move", lambda t: setattr(t.keyframes[1], "pos", t.keyframes[1].pos + (1 + 0.5j)))
    assert panel.current is not None and panel.current is not first
    assert picked[-1][1] is False

    # Fixing its pivots, then dragging one: the design follows the pivot.
    panel.fix_pivots()
    assert len(doc.target.pivots) >= 1
    g0 = doc.target.pivots[0].pos
    doc.edit("drag", lambda t: setattr(t.pivots[0], "pos", t.pivots[0].pos + 2j))
    assert any(abs(g - (g0 + 2j)) < 1e-9 for g in panel.current.grounds)
    panel.free_pivots()
    assert not doc.target.pivots

    panel.tabs.setCurrentIndex(1)
    assert panel.table.rowCount() == len(panel.result.rejected)
