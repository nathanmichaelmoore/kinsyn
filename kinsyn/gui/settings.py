"""User preferences (persisted with QSettings) and the Preferences dialog."""

from PySide6 import QtCore, QtGui, QtWidgets

from kinsyn.core.units import LENGTH_UNITS

DEFAULTS = {
    "ui/font_pt": 10.0,
    "ui/plot_font_pt": 9.0,
    "units/default": "mm",
    "analysis/mu_limit_deg": 40.0,
}
FONT_MIN, FONT_MAX = 7.0, 20.0


class Settings:
    def __init__(self):
        self.q = QtCore.QSettings("kinsyn", "kinsyn")

    def get(self, key):
        default = DEFAULTS[key]
        v = self.q.value(key, default)
        try:
            return type(default)(v)
        except (TypeError, ValueError):
            return default

    def set(self, key, value):
        self.q.setValue(key, value)

    def get_raw(self, key):
        return self.q.value(key)

    def set_raw(self, key, value):
        self.q.setValue(key, value)


def clamp_font(pt):
    return max(FONT_MIN, min(FONT_MAX, pt))


class PreferencesDialog(QtWidgets.QDialog):
    """Edits a copy of the settings; `applied` fires with the new values on
    every change so the window updates live."""

    applied = QtCore.Signal(dict)
    resetLayout = QtCore.Signal()

    def __init__(self, values, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.values = dict(values)
        form = QtWidgets.QFormLayout(self)

        self.font = QtWidgets.QDoubleSpinBox()
        self.font.setRange(FONT_MIN, FONT_MAX)
        self.font.setSingleStep(0.5)
        self.font.setSuffix(" pt")
        self.font.setValue(values["ui/font_pt"])
        form.addRow("Interface text size", self.font)

        self.plot_font = QtWidgets.QDoubleSpinBox()
        self.plot_font.setRange(FONT_MIN, FONT_MAX)
        self.plot_font.setSingleStep(0.5)
        self.plot_font.setSuffix(" pt")
        self.plot_font.setValue(values["ui/plot_font_pt"])
        form.addRow("Plot and canvas text size", self.plot_font)

        self.unit = QtWidgets.QComboBox()
        self.unit.addItems(list(LENGTH_UNITS))
        self.unit.setCurrentText(values["units/default"])
        form.addRow("Default units (new sessions)", self.unit)

        self.mu = QtWidgets.QDoubleSpinBox()
        self.mu.setRange(0.0, 89.0)
        self.mu.setSuffix(" °")
        self.mu.setValue(values["analysis/mu_limit_deg"])
        form.addRow("Minimum transmission angle", self.mu)

        reset = QtWidgets.QPushButton("Reset panel layout")
        reset.clicked.connect(self.resetLayout)
        form.addRow(reset)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.accept)
        form.addRow(buttons)

        for w in (self.font, self.plot_font, self.mu):
            w.valueChanged.connect(self._emit)
        self.unit.currentTextChanged.connect(self._emit)

    def _emit(self, *_):
        self.values.update({
            "ui/font_pt": self.font.value(),
            "ui/plot_font_pt": self.plot_font.value(),
            "units/default": self.unit.currentText(),
            "analysis/mu_limit_deg": self.mu.value(),
        })
        self.applied.emit(dict(self.values))


def apply_app_font(pt):
    app = QtWidgets.QApplication.instance()
    f = QtGui.QFont(app.font())
    f.setPointSizeF(pt)
    app.setFont(f)
