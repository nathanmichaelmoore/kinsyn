"""Target panel: mode, solver hint and warnings, inspector for the selected
keyframe, and a spreadsheet-style keyframe table (edit, reorder, paste)."""

import html
import math
import re

from PySide6 import QtCore, QtGui, QtWidgets

from kinsyn.core.target import MODES, TIMING_MODES, Keyframe
from kinsyn.core.units import format_angle, format_length, parse_angle, parse_length

from kinsyn.help.topics import tooltip

from .editor import ValueField

COLS = ["x", "y", "angle", "timing", "t", "tol"]
TIMING_LABEL = {"free": "free", "absolute": "abs", "relative": "rel"}


class TargetPanel(QtWidgets.QWidget):
    def __init__(self, doc):
        super().__init__()
        self.doc = doc
        self.unit = "mm"
        self._updating = False
        lay = QtWidgets.QVBoxLayout(self)

        top = QtWidgets.QFormLayout()
        self.mode = QtWidgets.QComboBox()
        self.mode.addItem("Motion generation (poses: position + angle)", "motion")
        self.mode.addItem("Path generation (points on a path)", "path")
        self.mode.activated.connect(self._on_mode)
        self.mode.setToolTip(tooltip("synthesis"))
        top.addRow("Synthesis", self.mode)
        lay.addLayout(top)
        self.notice = QtWidgets.QLabel(
            "<b>What this panel does:</b> describe the motion you <i>want</i> (poses, body, timing). "
            "The <b>Synthesis</b> tab then finds linkages that produce it (2 to 5 exact poses). "
            "<a href='help:tutorials/03-define-a-motion.md'>How to use the target editor</a>")
        self.notice.setWordWrap(True)
        self.notice.setOpenExternalLinks(False)
        self.notice.setTextFormat(QtCore.Qt.RichText)
        self.notice.setStyleSheet("QLabel { border: 1px solid palette(mid); border-radius: 6px; padding: 6px; }")
        lay.addWidget(self.notice)
        self.hint = QtWidgets.QLabel()
        self.hint.setWordWrap(True)
        self.hint.setTextFormat(QtCore.Qt.RichText)
        lay.addWidget(self.hint)

        # Inspector
        box = QtWidgets.QGroupBox("Selected keyframe")
        form = QtWidgets.QFormLayout(box)
        self.f_x = ValueField("length", self.unit)
        self.f_y = ValueField("length", self.unit)
        self.f_angle = ValueField("angle", self.unit)
        self.f_timing = QtWidgets.QComboBox()
        for m in TIMING_MODES:
            self.f_timing.addItem({"free": "Free (solver decides)", "absolute": "Prescribed input angle",
                                   "relative": "Relative to previous"}[m], m)
        self.f_t = ValueField("angle", self.unit)
        self.f_tol = ValueField("length", self.unit)
        self.f_tol_angle = ValueField("angle", self.unit)
        self.f_weight = QtWidgets.QDoubleSpinBox()
        self.f_weight.setRange(0.0, 1000.0)
        self.f_weight.setSingleStep(0.5)
        xy = QtWidgets.QWidget()
        xl = QtWidgets.QHBoxLayout(xy)
        xl.setContentsMargins(0, 0, 0, 0)
        for lbl, f in (("x", self.f_x), ("y", self.f_y)):
            xl.addWidget(QtWidgets.QLabel(lbl))
            xl.addWidget(f, 1)
        form.addRow("Position", xy)
        self.angle_label = QtWidgets.QLabel("Angle")
        form.addRow(self.angle_label, self.f_angle)
        form.addRow("Timing", self.f_timing)
        form.addRow("Input angle", self.f_t)
        form.addRow("Tolerance", self.f_tol)
        self.tol_angle_label = QtWidgets.QLabel("Angle tolerance")
        form.addRow(self.tol_angle_label, self.f_tol_angle)
        form.addRow("Weight", self.f_weight)
        self.inspector = box
        lay.addWidget(box)
        self.f_x.committed.connect(lambda v: self._set_sel("pos", complex(v, self.doc.selected_keyframe().pos.imag)))
        self.f_y.committed.connect(lambda v: self._set_sel("pos", complex(self.doc.selected_keyframe().pos.real, v)))
        self.f_angle.committed.connect(lambda v: self._set_sel("angle", v))
        self.f_timing.activated.connect(lambda _: self._set_sel("timing", self.f_timing.currentData()))
        self.f_t.committed.connect(lambda v: self._set_sel("t", v))
        self.f_tol.committed.connect(lambda v: self._set_sel("tol", max(0.0, v)))
        self.f_tol_angle.committed.connect(lambda v: self._set_sel("tol_angle", max(0.0, v)))
        self.f_weight.editingFinished.connect(lambda: self._set_sel("weight", self.f_weight.value()))

        # Table
        self.table = QtWidgets.QTableWidget(0, len(COLS))
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.itemChanged.connect(self._on_cell)
        self.table.itemSelectionChanged.connect(self._on_table_select)
        lay.addWidget(self.table, 1)
        row = QtWidgets.QHBoxLayout()
        for label, tip, fn in (("↑", "Move up", lambda: self._move(-1)), ("↓", "Move down", lambda: self._move(1)),
                               ("Delete", "Delete the selected keyframe", self.delete_selected),
                               ("Paste", "Paste rows of x, y[, angle] from a spreadsheet or CSV", self.paste),
                               ("Clear body", "Remove the body outline", self._clear_body)):
            b = QtWidgets.QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)

        # Curves, zones and fixed pivots
        self.items_list = QtWidgets.QListWidget()
        self.items_list.setMaximumHeight(110)
        self.items_list.setToolTip("Curves, pivot zones and fixed pivots. Select one to highlight it on the canvas.")
        self.items_list.currentRowChanged.connect(self._on_item_row)
        lay.addWidget(QtWidgets.QLabel("Curves, zones and fixed pivots"))
        lay.addWidget(self.items_list)
        irow = QtWidgets.QHBoxLayout()
        self.toggle_btn = QtWidgets.QPushButton("Open / close curve")
        self.toggle_btn.clicked.connect(self._toggle_item)
        del_btn = QtWidgets.QPushButton("Delete")
        del_btn.clicked.connect(lambda: self.doc.selected_item and self.doc.delete_selection())
        irow.addWidget(self.toggle_btn)
        irow.addWidget(del_btn)
        lay.addLayout(irow)

        doc.changed.connect(self.refresh)
        doc.selectionChanged.connect(self.refresh)
        self.refresh()

    # --- updates from the document ---------------------------------------
    def set_units(self, unit):
        self.unit = unit
        for f in (self.f_x, self.f_y, self.f_tol):
            f.set_unit(unit)
        self.refresh()

    def refresh(self):
        self._updating = True
        t = self.doc.target
        motion = t.mode == "motion"
        self.mode.setCurrentIndex(MODES.index(t.mode))
        warn = "".join(f"<br><span style='color:#ef5350'>⚠ {html.escape(m)}</span>" for _, m in t.warnings())
        self.hint.setText(f"<b>{html.escape(t.solver_hint())}</b>{warn}")

        k = self.doc.selected_keyframe()
        self.inspector.setEnabled(k is not None)
        self.inspector.setTitle(f"Keyframe {t.index_of(k.id) + 1}" if k else "Selected keyframe (none)")
        for w in (self.angle_label, self.f_angle, self.tol_angle_label, self.f_tol_angle):
            w.setVisible(motion)
        if k:
            self.f_x.set_value(k.pos.real)
            self.f_y.set_value(k.pos.imag)
            self.f_angle.set_value(k.angle)
            self.f_timing.setCurrentIndex(TIMING_MODES.index(k.timing))
            self.f_t.set_value(k.t)
            self.f_t.setEnabled(k.timing != "free")
            self.f_tol.set_value(k.tol)
            self.f_tol_angle.set_value(k.tol_angle)
            self.f_weight.setValue(k.weight)

        self.table.setColumnHidden(2, not motion)
        headers = [f"x ({self.unit})", f"y ({self.unit})", "angle (°)", "timing", "t (°)", f"tol ({self.unit})"]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(t.keyframes))
        for r, kf in enumerate(t.keyframes):
            vals = [format_length(kf.pos.real, self.unit), format_length(kf.pos.imag, self.unit),
                    format_angle(kf.angle, 2), TIMING_LABEL[kf.timing],
                    format_angle(kf.t, 2) if kf.timing != "free" else "", format_length(kf.tol, self.unit)]
            for c, v in enumerate(vals):
                item = QtWidgets.QTableWidgetItem(v)
                if c == 3:
                    item.setToolTip("free, abs or rel")
                self.table.setItem(r, c, item)
        self._items = ([("curve", c.id, f"Curve: {len(c.points)} points, {'closed' if c.closed else 'open'}")
                        for c in t.curves]
                       + [("zone", z.id, f"{'Allowed pivot zone' if z.allow else 'Keep-out zone'}: "
                                         f"{len(z.polygon)} corners") for z in t.zones]
                       + [("pivot", f.id, ("Fixed slider axis at " if f.slider_angle is not None else "Fixed pivot at ")
                           + f"({format_length(f.pos.real, self.unit)}, {format_length(f.pos.imag, self.unit)}) "
                             f"{self.unit}") for f in t.pivots])
        self.items_list.blockSignals(True)
        self.items_list.clear()
        for _, _, label in self._items:
            self.items_list.addItem(label)
        si = self.doc.selected_item
        rows = [i for i, (k, iid, _) in enumerate(self._items) if si and si[1] == iid]
        self.items_list.setCurrentRow(rows[0] if rows else -1)
        self.items_list.blockSignals(False)
        kind = si[0] if si else None
        self.toggle_btn.setEnabled(kind in ("curve", "zone"))
        self.toggle_btn.setText("Allowed / keep-out" if kind == "zone" else "Open / close curve")

        sel = t.index_of(self.doc.selected) if self.doc.selected else None
        if sel is None:
            self.table.clearSelection()
        else:
            self.table.selectRow(sel)
        self._updating = False

    # --- edits -----------------------------------------------------------
    def _on_mode(self, _):
        mode = self.mode.currentData()
        if mode != self.doc.target.mode:
            self.doc.edit("Change synthesis mode", lambda t: setattr(t, "mode", mode))

    def _set_sel(self, attr, value):
        k = self.doc.selected_keyframe()
        if k is None or self._updating:
            return
        self.doc.edit(f"Edit keyframe {attr}", lambda t: setattr(t.keyframe(k.id), attr, value))

    def _on_table_select(self):
        if self._updating:
            return
        rows = self.table.selectionModel().selectedRows()
        ks = self.doc.target.keyframes
        if rows and rows[0].row() < len(ks):
            self.doc.select(ks[rows[0].row()].id)

    def _on_cell(self, item):
        if self._updating:
            return
        r, c = item.row(), item.column()
        kid = self.doc.target.keyframes[r].id
        text = item.text().strip()
        try:
            if c in (0, 1):
                v = parse_length(text, self.unit)

                def fn(t):
                    k = t.keyframe(kid)
                    k.pos = complex(v, k.pos.imag) if c == 0 else complex(k.pos.real, v)
            elif c == 2:
                v = parse_angle(text)
                fn = lambda t: setattr(t.keyframe(kid), "angle", v)
            elif c == 3:
                mode = {"free": "free", "abs": "absolute", "absolute": "absolute",
                        "rel": "relative", "relative": "relative"}[text.lower()]
                fn = lambda t: setattr(t.keyframe(kid), "timing", mode)
            elif c == 4:
                v = parse_angle(text)

                def fn(t):
                    k = t.keyframe(kid)
                    k.t = v
                    if k.timing == "free":
                        k.timing = "absolute"
            else:
                v = max(0.0, parse_length(text, self.unit))
                fn = lambda t: setattr(t.keyframe(kid), "tol", v)
        except (ValueError, KeyError):
            QtCore.QTimer.singleShot(0, self.refresh)  # restore the previous text
            return
        self.doc.edit("Edit keyframe", fn)

    def _on_item_row(self, row):
        if 0 <= row < len(self._items):
            kind, iid, _ = self._items[row]
            self.doc.select_item((kind, iid, None))

    def _toggle_item(self):
        si = self.doc.selected_item
        if not si:
            return
        kind, iid, _ = si
        if kind == "curve":
            self.doc.edit("Open / close curve", lambda t: [setattr(c, "closed", not c.closed)
                                                           for c in t.curves if c.id == iid])
        elif kind == "zone":
            self.doc.edit("Toggle zone type", lambda t: [setattr(z, "allow", not z.allow)
                                                         for z in t.zones if z.id == iid])

    def _move(self, d):
        k = self.doc.selected_keyframe()
        if k is None:
            return
        i = self.doc.target.index_of(k.id)
        j = i + d
        if not 0 <= j < len(self.doc.target.keyframes):
            return

        def fn(t):
            t.keyframes[i], t.keyframes[j] = t.keyframes[j], t.keyframes[i]
        self.doc.edit("Reorder keyframes", fn)

    def delete_selected(self):
        self.doc.delete_selection()

    def _clear_body(self):
        if self.doc.target.body is not None:
            self.doc.edit("Clear body outline", lambda t: setattr(t, "body", None))

    def paste(self):
        text = QtWidgets.QApplication.clipboard().text()
        try:
            rows = parse_table(text, self.unit)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Paste keyframes", f"Could not read the clipboard: {exc}")
            return
        if rows:
            self.doc.edit(f"Paste {len(rows)} keyframes",
                          lambda t: t.keyframes.extend(Keyframe(pos=p, angle=a or 0.0) for p, a in rows))


def parse_table(text, unit):
    """Rows of 'x y [angle]' separated by tabs, commas, semicolons or spaces.
    A non-numeric first row is treated as a header and skipped."""
    rows = []
    for n, line in enumerate(l for l in text.splitlines() if l.strip()):
        cells = [c for c in re.split(r"[\t,;]+|\s{2,}|\s(?=[-+.\d])", line.strip()) if c.strip()]
        try:
            x, y = parse_length(cells[0], unit), parse_length(cells[1], unit)
            a = parse_angle(cells[2]) if len(cells) > 2 else None
        except (ValueError, IndexError):
            if n == 0:
                continue
            raise ValueError(f"line {n + 1}: {line.strip()!r}")
        rows.append((complex(x, y), a))
    return rows
