"""Parameter editor: a form generated from a mechanism's Param specs, with a
live slider for every scalar dimension."""

import math

from PySide6 import QtCore, QtWidgets

import kinsyn.core.families  # noqa: F401  (registers mechanism types)
from kinsyn.core.mechanism import REGISTRY
from kinsyn.core.units import format_angle, format_length, parse_angle, parse_length

SLIDER_STEPS = 1000
ERROR_STYLE = "QLineEdit { border: 1px solid #ef5350; }"


class ValueField(QtWidgets.QLineEdit):
    """Line edit showing an internal value (mm or rad) in display units."""

    committed = QtCore.Signal(float)

    def __init__(self, kind, unit):
        super().__init__()
        self.kind, self.unit, self.value = kind, unit, 0.0
        self.editingFinished.connect(self._commit)
        self.setMinimumWidth(70)

    def set_value(self, v):
        self.value = v
        self.setText(format_angle(v) if self.kind == "angle" else format_length(v, self.unit))
        self.setStyleSheet("")

    def set_unit(self, unit):
        self.unit = unit
        self.set_value(self.value)

    def _commit(self):
        try:
            v = parse_angle(self.text()) if self.kind == "angle" else parse_length(self.text(), self.unit)
        except ValueError:
            self.setStyleSheet(ERROR_STYLE)
            self.setToolTip("Could not parse. Examples: 12.5, 2.5in, 1 1/4\", 2*25.4, 30deg")
            return
        self.setStyleSheet("")
        if v != self.value:
            self.value = v
            self.committed.emit(v)
        self.set_value(v)


class ScalarRow(QtWidgets.QWidget):
    changed = QtCore.Signal(float)

    def __init__(self, kind, unit, value, rng=None):
        super().__init__()
        self.kind = kind
        self.field = ValueField("angle" if kind == "angle" else "length", unit)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, SLIDER_STEPS)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.field, 2)
        lay.addWidget(self.slider, 3)
        self.lo, self.hi = rng or self._auto_range(value)
        self.field.set_value(value)
        self._sync_slider(value)
        self.field.committed.connect(self._from_field)
        self.slider.valueChanged.connect(self._from_slider)

    def _auto_range(self, v):
        if self.kind == "angle":
            return -math.pi, math.pi
        if self.kind == "signed_length":
            r = max(2 * abs(v), 50.0)
            return -r, r
        return max(0.0, 0.2 * v), max(3 * v, 50.0)

    def _sync_slider(self, v):
        if v < self.lo or v > self.hi:
            self.lo, self.hi = min(self.lo, v), max(self.hi, v)
        self.slider.blockSignals(True)
        self.slider.setValue(round((v - self.lo) / (self.hi - self.lo) * SLIDER_STEPS))
        self.slider.blockSignals(False)

    def _from_field(self, v):
        self._sync_slider(v)
        self.changed.emit(v)

    def _from_slider(self, i):
        v = self.lo + (self.hi - self.lo) * i / SLIDER_STEPS
        self.field.set_value(v)
        self.changed.emit(v)

    def set_unit(self, unit):
        self.field.set_unit(unit)


class PointRow(QtWidgets.QWidget):
    changed = QtCore.Signal(complex)

    def __init__(self, unit, value):
        super().__init__()
        self.x, self.y = ValueField("length", unit), ValueField("length", unit)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for lbl, f in (("x", self.x), ("y", self.y)):
            lay.addWidget(QtWidgets.QLabel(lbl))
            lay.addWidget(f, 1)
            f.committed.connect(self._emit)
        self.x.set_value(value.real)
        self.y.set_value(value.imag)

    def _emit(self, _):
        self.changed.emit(complex(self.x.value, self.y.value))

    def set_unit(self, unit):
        self.x.set_unit(unit)
        self.y.set_unit(unit)


class ParamEditor(QtWidgets.QWidget):
    """Emits `changed(mechanism)` whenever a parameter is edited."""

    changed = QtCore.Signal(object)
    typeChanged = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.unit = "mm"
        self.mech = None
        self.rows = {}
        outer = QtWidgets.QVBoxLayout(self)
        self.type_combo = QtWidgets.QComboBox()
        for kind, cls in REGISTRY.items():
            self.type_combo.addItem(cls.title, kind)
        self.type_combo.activated.connect(lambda _: self.typeChanged.emit(self.type_combo.currentData()))
        outer.addWidget(self.type_combo)
        self.form_host = QtWidgets.QWidget()
        self.form = QtWidgets.QFormLayout(self.form_host)
        self.form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        outer.addWidget(self.form_host)

    def set_mechanism(self, mech, rebuild=True):
        """Show `mech`. Rebuilds the form (resetting slider ranges) when the
        type changes or `rebuild` is set; otherwise only refreshes values."""
        same_kind = self.mech is not None and self.mech.kind == mech.kind
        self.mech = mech
        self.type_combo.setCurrentIndex(self.type_combo.findData(mech.kind))
        if rebuild or not same_kind:
            self._build()

    def _build(self):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.rows = {}
        for p in self.mech.params:
            v = getattr(self.mech, p.name)
            if p.kind in ("length", "signed_length", "angle"):
                row = ScalarRow(p.kind, self.unit, v)
                row.changed.connect(lambda val, n=p.name: self._set(n, val))
            elif p.kind == "point":
                row = PointRow(self.unit, complex(v))
                row.changed.connect(lambda val, n=p.name: self._set(n, val))
            elif p.kind == "branch":
                row = QtWidgets.QComboBox()
                row.addItem("+1", 1)
                row.addItem("-1", -1)
                row.setCurrentIndex(0 if v == 1 else 1)
                row.activated.connect(lambda _, n=p.name, w=row: self._set(n, w.currentData()))
            else:
                row = QtWidgets.QComboBox()
                for c in p.choices:
                    row.addItem(c, c)
                row.setCurrentIndex(p.choices.index(v))
                row.activated.connect(lambda _, n=p.name, w=row: self._set(n, w.currentData()))
            self.rows[p.name] = row
            label = QtWidgets.QLabel(p.label)
            if p.help:
                label.setToolTip(p.help)
                row.setToolTip(p.help)
            self.form.addRow(label, row)

    def _set(self, name, value):
        self.mech = self.mech.copy(**{name: value})
        self.changed.emit(self.mech)

    def set_units(self, unit):
        self.unit = unit
        for row in self.rows.values():
            if hasattr(row, "set_unit"):
                row.set_unit(unit)
