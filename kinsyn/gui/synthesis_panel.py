"""Synthesis panel: turns the target poses into candidate linkages.

Shows which method applies, the search options, a sortable table of valid
designs (and of rejected ones, with the reason), and keeps the selected
design in step with the target: when a pose or a fixed pivot moves, the
same design (same free choices) is re-solved at once, and the full search
re-runs in the background."""

import html
import math
from dataclasses import replace

from PySide6 import QtCore, QtGui, QtWidgets

from kinsyn.core.target import FixedPivot
from kinsyn.core.units import format_length
from kinsyn.help.topics import TERMS, tooltip
from kinsyn.synthesis.motion import FAMILIES, INPUT_MOTIONS, Options, resolve_candidate, solve_motion

from . import crashlog

COLS = ["Type", "Input", "Class", "μ min", "Ratio", "Size", "Why rejected"]
TYPE_SHORT = {"fourbar": "Four-bar", "slider_crank": "Slider-crank", "inverted_slider": "Inverted slider"}
INPUT_SHORT = {"crank": "crank", "slider": "slider", "cylinder": "cylinder"}
CLASS_SHORT = {
    "Crank-rocker": "crank-rocker", "Rocker-crank": "rocker-crank", "Double-crank (drag link)": "double-crank",
    "Double-rocker (Grashof)": "double-rocker", "Triple-rocker (non-Grashof)": "triple-rocker",
}
GOOD, BAD = "#66bb6a", "#ef5350"
SIZE_DIGITS = {"mm": 1, "cm": 2, "m": 4, "in": 2}


# Sort keys per column. The panel sorts the rows itself: overriding
# QTableWidgetItem.__lt__ for numeric sorting segfaults with PySide6 6.11 on
# Python 3.14 (2026-10-19).
SORT_KEYS = [
    lambda c: TYPE_SHORT.get(c.family, c.family),
    lambda c: c.input_name(),
    lambda c: c.classification,
    lambda c: -math.degrees(c.mu_min) if math.isfinite(c.mu_min) else 1.0,  # best first
    lambda c: c.ratio,
    lambda c: c.size,
    lambda c: c.why(),
]


class _Signals(QtCore.QObject):
    done = QtCore.Signal(int, object)


class _Job(QtCore.QRunnable):
    def __init__(self, fn, gen, signals):
        super().__init__()
        self.fn, self.gen, self.signals = fn, gen, signals

    def run(self):
        try:
            res = self.fn()
        except Exception as exc:  # reported in the panel, and logged
            crashlog.breadcrumb(f"synthesis failed: {exc!r}")
            res = exc
        self.signals.done.emit(self.gen, res)


def same_design(a, b):
    return (a.family == b.family and a.mech.to_dict().get("driver") == b.mech.to_dict().get("driver")
            and [(d.kind, d.source) for d in a.dyads] == [(d.kind, d.source) for d in b.dyads])


class SynthesisPanel(QtWidgets.QWidget):
    designSelected = QtCore.Signal(object, bool)  # candidate, newly picked (vs. tracked)
    resultChanged = QtCore.Signal(object)  # motion.Result or None
    linkActivated = QtCore.Signal(str)

    def __init__(self, doc, mu_limit):
        super().__init__()
        self.doc = doc
        self.unit = "mm"
        self.result = None
        self.rows = []  # candidates in table order (before sorting)
        self.current = None  # the design shown on the canvas
        self._fixed_ids = []  # per dyad of `current`: id of the fixed pivot it uses, or None
        self._gen = 0
        self._running = False
        self._pending = False
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self._timer = QtCore.QTimer(self, singleShot=True, interval=250, timeout=self.solve)

        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Turns the poses on the <b>Target</b> tab into linkages that pass through them. "
            "Pick a design in the table to see it move. "
            "<a href='help:tutorials/04-motion-generation.md'>Tutorial</a>")
        intro.setWordWrap(True)
        intro.setTextFormat(QtCore.Qt.RichText)
        intro.linkActivated.connect(self.linkActivated)
        lay.addWidget(intro)
        self.method = QtWidgets.QLabel()
        self.method.setWordWrap(True)
        self.method.setTextFormat(QtCore.Qt.RichText)
        self.method.setToolTip(tooltip("synthesis") + "<br><br>" + tooltip("dyad"))
        lay.addWidget(self.method)

        box = QtWidgets.QGroupBox("Search")
        form = QtWidgets.QFormLayout(box)
        fams = QtWidgets.QVBoxLayout()
        self.family_checks = {}
        fam_tips = {
            "fourbar": "Four-bar: two pin-jointed links connect the moving body to the ground.",
            "slider_crank": "Slider-crank: one link is replaced by a block sliding on a straight ground rail.",
            "inverted_slider": "Inverted slider-crank: the moving body slides through a pivoting swivel "
                               "(a slotted lever, or a rod through a swivel block or cylinder).",
        }
        for key, label in FAMILIES.items():
            cb = QtWidgets.QCheckBox(label, checked=True)
            cb.setToolTip(fam_tips[key])
            cb.toggled.connect(self.schedule)
            fams.addWidget(cb)
            self.family_checks[key] = cb
        form.addRow("Types", fams)
        self.input_motion = QtWidgets.QComboBox()
        for key, (label, _) in INPUT_MOTIONS.items():
            self.input_motion.addItem(label, key)
        self.input_motion.setToolTip(
            "Whether the input must turn all the way round. A rocking input (one that swings back and forth "
            "between two limits) is fine for most hand- or cylinder-driven mechanisms.<br>" + tooltip("grashof"))
        self.input_motion.activated.connect(self.schedule)
        form.addRow("Input motion", self.input_motion)
        self.mu_min = QtWidgets.QDoubleSpinBox(suffix="°", decimals=0, minimum=0, maximum=89)
        self.mu_min.setValue(math.degrees(mu_limit))
        self.mu_min.setToolTip("Reject designs whose transmission angle gets closer than this to 0° or 180° "
                               "anywhere between the first and the last pose.<br>" + tooltip("transmission-angle"))
        self.mu_min.valueChanged.connect(self.schedule)
        form.addRow("Min transmission angle", self.mu_min)
        self.max_ratio = QtWidgets.QDoubleSpinBox(decimals=1, minimum=1.5, maximum=100, singleStep=1)
        self.max_ratio.setValue(Options.max_ratio)
        self.max_ratio.setToolTip("Reject designs whose longest link is more than this many times its shortest.")
        self.max_ratio.valueChanged.connect(self.schedule)
        form.addRow("Max link length ratio", self.max_ratio)
        row = QtWidgets.QHBoxLayout()
        self.live = QtWidgets.QCheckBox("Re-solve while editing", checked=True)
        self.live.setToolTip("Search again whenever the poses, zones or fixed pivots change.")
        self.live.toggled.connect(lambda on: on and self.schedule())
        row.addWidget(self.live, 1)
        self.solve_btn = QtWidgets.QPushButton("Solve")
        self.solve_btn.setToolTip("Search for designs now")
        self.solve_btn.clicked.connect(self.solve)
        row.addWidget(self.solve_btn)
        form.addRow(row)
        lay.addWidget(box)

        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(self.status)
        # 4 and 5 poses: what the curves on the canvas mean.
        self.show_curves = QtWidgets.QCheckBox("Show Burmester curves on the canvas", checked=True)
        self.show_curves.setToolTip(tooltip("center-point-curve"))
        lay.addWidget(self.show_curves)
        self.legend = QtWidgets.QLabel(
            "<span style='color:#ffb74d'>━</span> center-point curve: where a ground pivot can go · "
            "<span style='color:#66bb6a'>━</span> used by valid designs · "
            "<span style='color:#80cbc4'>┅</span> circle-point curve: the matching moving pivots · "
            "<span style='color:#ffd54f'>★</span> Burmester points · "
            "<span style='color:#f48fb1'>■</span> slider options. "
            "Place a fixed pivot (G) on the curve to choose it yourself.")
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(self.legend)
        self.show_curves.setVisible(False)
        self.legend.setVisible(False)

        self.tabs = QtWidgets.QTabBar()
        self.tabs.addTab("Designs")
        self.tabs.addTab("Rejected")
        self.tabs.setTabToolTip(0, "Designs that pass every check, best first")
        self.tabs.setTabToolTip(1, "The most promising designs that were ruled out, and why.<br>"
                                + "<br>".join(f"<b>{TERMS[k][0]}</b>: {TERMS[k][1]}"
                                              for k in ("branch-defect", "order-defect", "circuit-defect")))
        self.tabs.currentChanged.connect(lambda _: self._fill_table())
        lay.addWidget(self.tabs)
        self.table = QtWidgets.QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        tips = ["Mechanism type", "What drives it", "Grashof class (whether the input can turn fully)",
                "Worst transmission angle between the first and last pose (higher is better)",
                "Longest link divided by the shortest (lower is more compact)",
                "Longest link", "The first check the design failed"]
        for i, t in enumerate(tips):
            self.table.horizontalHeaderItem(i).setToolTip(t)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.sort_col, self.sort_desc = None, False  # None: solver's ranking
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.setMinimumHeight(220)
        lay.addWidget(self.table, 1)

        self.detail = QtWidgets.QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(self.detail)
        brow = QtWidgets.QHBoxLayout()
        self.fix_btn = QtWidgets.QPushButton("Fix its pivots")
        self.fix_btn.setToolTip("Turn this design's ground pivots into fixed pivots. The search then keeps "
                                "them, and you can drag them on the canvas to explore nearby designs.<br><br>"
                                + tooltip("fixed-pivot"))
        self.fix_btn.clicked.connect(self.fix_pivots)
        self.unfix_btn = QtWidgets.QPushButton("Free all pivots")
        self.unfix_btn.setToolTip("Remove every fixed pivot from the target, so the search can place them anywhere")
        self.unfix_btn.clicked.connect(self.free_pivots)
        brow.addWidget(self.fix_btn)
        brow.addWidget(self.unfix_btn)
        lay.addLayout(brow)

        doc.changed.connect(self._on_target_changed)
        self._update_buttons()
        self._on_target_changed()

    # --- options ---------------------------------------------------------
    def options(self):
        return Options(families=tuple(k for k, cb in self.family_checks.items() if cb.isChecked()),
                       input_motion=self.input_motion.currentData(), mu_min=math.radians(self.mu_min.value()),
                       max_ratio=self.max_ratio.value())

    def set_units(self, unit):
        self.unit = unit
        self._fill_table()
        self._show_detail()

    # --- solving -----------------------------------------------------------
    def schedule(self, *_):
        if self.live.isChecked():
            self._timer.start()

    def solve(self):
        self._timer.stop()
        t = self.doc.target.copy()
        if t.mode != "motion":
            self._show_result(None)
            return
        opts = self.options()
        self._gen += 1
        gen = self._gen
        kfs, zones, fixed = t.keyframes, t.zones, t.pivots

        def job():
            return solve_motion(kfs, opts, zones, fixed, should_stop=lambda: self._gen != gen)

        if len(fixed) >= 2 or len(kfs) < 2 or len(kfs) > 3:
            # Small (or trivial) problem: answer right away.
            self._on_done(gen, job())
            return
        if self._running:
            self._pending = True
            return
        self._running = True
        self.status.setText("<i>Searching…</i>")
        QtCore.QThreadPool.globalInstance().start(_Job(job, gen, self._signals))

    def _on_done(self, gen, res):
        self._running = False
        if self._pending:
            self._pending = False
            self.solve()
            return
        if gen != self._gen or res is None:
            return
        if isinstance(res, Exception):
            self.status.setText(f"<span style='color:{BAD}'>The search failed: {html.escape(str(res))}</span>")
            return
        self._show_result(res)

    def shutdown(self):
        """Make a search still running in the background give up."""
        self._gen += 1
        self._timer.stop()

    def _show_result(self, res):
        self.result = res
        has_curves = res is not None and bool(res.curves)
        self.show_curves.setVisible(has_curves)
        self.legend.setVisible(has_curves)
        self.resultChanged.emit(res)
        if res is not None:
            crashlog.breadcrumb(f"synthesis: {res.method}; {len(res.solutions)} designs, "
                                f"{res.evaluated} combinations")
        if res is None:
            self.method.setText("Motion generation only for now: path generation is a later milestone.")
            self.status.setText("")
            self.rows = []
            self._fill_table()
            return
        self.method.setText(f"<b>{html.escape(res.method)}</b>")
        parts = []
        if res.evaluated:
            parts.append(f"<span style='color:{GOOD}'>{len(res.solutions)} design(s)</span> from "
                         f"{res.evaluated:,} combinations")
            if res.reject_counts:
                top = ", ".join(f"{n:,} {html.escape(k)}" for k, n in res.reject_counts.most_common(4))
                parts.append(f"rejected: {top}")
        parts += [html.escape(n) for n in res.notes]
        if res.evaluated and not res.solutions:
            parts.append("Nothing passed every check. Try relaxing the options, moving the poses, "
                         "or look at the <b>Rejected</b> tab.")
        self.status.setText("<br>".join(parts))
        self._fill_table()

    # --- table ---------------------------------------------------------------
    def _candidates(self):
        if self.result is None:
            return []
        if self.tabs.currentIndex() == 1:
            return list(self.result.rejected)
        rows = list(self.result.solutions)
        if self.current is not None and not any(same_design(c, self.current) for c in rows) \
                and self.current.valid:
            rows.insert(0, self.current)
        return rows

    def _on_header(self, col):
        if self.sort_col == col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col, self.sort_desc = col, False
        self._fill_table()

    def _fill_table(self):
        self.tabs.setTabText(0, f"Designs ({len(self.result.solutions)})" if self.result else "Designs")
        self.tabs.setTabText(1, f"Rejected ({sum(self.result.reject_counts.values()):,})"
                             if self.result else "Rejected")
        self.rows = self._candidates()
        self.table.horizontalHeaderItem(5).setText(f"Size ({self.unit})")
        header = self.table.horizontalHeader()
        if self.sort_col is not None:
            self.rows.sort(key=SORT_KEYS[self.sort_col], reverse=self.sort_desc)
            header.setSortIndicatorShown(True)
            header.setSortIndicator(self.sort_col, QtCore.Qt.DescendingOrder if self.sort_desc
                                    else QtCore.Qt.AscendingOrder)
        else:
            header.setSortIndicatorShown(False)
        tbl = self.table
        tbl.blockSignals(True)
        tbl.clearContents()
        tbl.setRowCount(len(self.rows))
        selected_row = None
        for r, c in enumerate(self.rows):
            mu = c.mu_min
            texts = [
                TYPE_SHORT.get(c.family, c.family),
                INPUT_SHORT.get(c.input_name(), c.input_name()),
                CLASS_SHORT.get(c.classification, c.classification.split(" (")[0].lower()),
                f"{math.degrees(mu):.0f}°" if math.isfinite(mu) else "–",
                f"{c.ratio:.1f}",
                format_length(c.size, self.unit, SIZE_DIGITS[self.unit]),
                c.why() if c.reasons else "",
            ]
            cells = [QtWidgets.QTableWidgetItem(t) for t in texts]
            for col, it in enumerate(cells):
                if c.reasons:
                    it.setToolTip(html.escape(c.why()))
                tbl.setItem(r, col, it)
            cells[6].setForeground(QtGui.QColor(BAD))
            if self.current is not None and same_design(c, self.current):
                selected_row = r
        tbl.setColumnHidden(6, self.tabs.currentIndex() == 0)
        if selected_row is not None:
            tbl.selectRow(selected_row)
        else:
            tbl.clearSelection()
        tbl.blockSignals(False)
        self._update_buttons()

    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return
        c = self.rows[items[0].row()]
        crashlog.breadcrumb(f"pick design {c.family} {c.input_name()} {c.classification}")
        self._set_current(c, picked=True)

    def _set_current(self, c, picked=False):
        self.current = c
        self._fixed_ids = [self._fixed_pivot_for(d) for d in c.dyads]
        self._show_detail()
        self._update_buttons()
        self.designSelected.emit(c, picked)

    def forget_current(self):
        """The mechanism was changed by hand: stop tracking the design."""
        if self.current is not None:
            self.current = None
            self._fixed_ids = []
            self.table.blockSignals(True)
            self.table.clearSelection()
            self.table.blockSignals(False)
            self._show_detail()
            self._update_buttons()

    def _show_detail(self):
        c = self.current
        if c is None:
            self.detail.setText("")
            return
        mu = f"{math.degrees(c.mu_min):.0f}°" if math.isfinite(c.mu_min) else "n/a"
        rot = "turns fully" if c.full_rotation else "rocks"
        text = (f"<b>{FAMILIES[c.family]}</b> driven by its {c.input_name()} ({rot}) · "
                f"{html.escape(c.classification)} · worst transmission angle {mu} · link ratio {c.ratio:.1f}")
        if c.reasons:
            text += f"<br><span style='color:{BAD}'>Rejected: {html.escape(c.why())}</span>"
        self.detail.setText(text)

    def _update_buttons(self):
        self.fix_btn.setEnabled(self.current is not None)
        self.unfix_btn.setEnabled(bool(self.doc.target.pivots))

    # --- following the target --------------------------------------------
    def _fixed_pivot_for(self, d):
        for p in self.doc.target.pivots:
            if d.kind in ("RR", "RP") and p.slider_angle is None and d.G is not None and abs(p.pos - d.G) < 1e-9:
                return p.id
            if d.kind == "PR" and p.slider_angle is not None and abs(p.slider_angle - d.angle) < 1e-12:
                return p.id
        return None

    def _remapped(self, c):
        """The design with its fixed-pivot free choices moved to where those
        pivots are now."""
        dyads = []
        pivots = {p.id: p for p in self.doc.target.pivots}
        for d, pid in zip(c.dyads, self._fixed_ids):
            p = pivots.get(pid)
            if p is not None and d.source:
                tag = d.source[0]
                if tag == "G" and p.slider_angle is None:
                    d = replace(d, source=("G", p.pos, d.source[2]))
                elif tag == "timed" and d.source[1] is not None:
                    d = replace(d, source=("timed", p.pos))
                elif tag == "gamma" and p.slider_angle is not None:
                    d = replace(d, source=("gamma", p.slider_angle, d.source[2]))
            dyads.append(d)
        return replace(c, dyads=tuple(dyads))

    def _on_target_changed(self):
        self._update_buttons()
        t = self.doc.target
        if t.mode != "motion":
            self._show_result(None)
            return
        if self.current is not None:
            # Fixed pivots added since the design was picked (e.g. "Fix its pivots").
            self._fixed_ids = [pid or self._fixed_pivot_for(d) for d, pid in zip(self.current.dyads, self._fixed_ids)]
            c2 = None
            if len(t.keyframes) == len(self.current.q):
                c2 = resolve_candidate(self._remapped(self.current), t.keyframes, self.options(), t.zones)
            if c2 is None:
                self.status.setText("The design you picked no longer exists for these poses.")
                self.forget_current()
            else:
                self._set_current(c2)
        if self.live.isChecked():
            self.schedule()

    # --- actions -----------------------------------------------------------
    def fix_pivots(self):
        c = self.current
        if c is None:
            return
        k1 = self.doc.target.keyframes[0]
        new = []
        for d in c.dyads:
            if d.kind in ("RR", "RP"):
                new.append(FixedPivot(d.G))
            elif d.kind == "PR":
                # The rail, marked where the slider block sits at pose 1.
                block = k1.pos + d.m * complex(math.cos(k1.angle), math.sin(k1.angle))
                new.append(FixedPivot(block, slider_angle=d.angle))

        def fn(t):
            t.pivots = [p for p in t.pivots
                        if not any(abs(p.pos - n.pos) < 1e-9 and p.slider_angle == n.slider_angle for n in new)]
            t.pivots.extend(new)
        self.doc.edit("Fix design pivots", fn)

    def free_pivots(self):
        if self.doc.target.pivots:
            self.doc.edit("Free all pivots", lambda t: setattr(t, "pivots", []))
