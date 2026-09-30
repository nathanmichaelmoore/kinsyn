"""Image and DXF underlays: reference drawings to trace over.

Each underlay has a placement (position of its origin in mm, rotation,
scale) and display settings. Images are calibrated by clicking two points
and typing the real distance; DXF geometry can be snapped to and turned
into a body, path or pivot zone."""

import cmath
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from kinsyn.core.dxf import INSUNITS_MM, distance_to_polyline, load_dxf
from kinsyn.core.target import Body, Curve, Keyframe, Zone, pose_inverse, simplify
from kinsyn.core.units import format_angle, format_length, parse_length

from . import crashlog
from .editor import ValueField
from .tools import SNAP_PX, Tool

DXF_COLOR = "#9fa8da"


@dataclass
class Underlay:
    kind: str  # "image" | "dxf"
    path: str
    pos: complex = 0j  # where the underlay's origin sits, mm
    rotation: float = 0.0
    scale: float = 1.0  # image: mm per pixel; dxf: extra scale factor
    opacity: float = 0.6
    visible: bool = True
    locked: bool = False
    units_override: float | None = None  # dxf: mm per drawing unit
    hidden_layers: list = field(default_factory=list)
    missing: bool = False

    @property
    def name(self):
        return Path(self.path).name

    def world(self, z):
        """Underlay-local coordinates (image px with y up, or DXF mm) -> world mm."""
        return self.pos + np.asarray(z, complex) * self.scale * np.exp(1j * self.rotation)

    def local(self, w):
        return (np.asarray(w, complex) - self.pos) / (self.scale * np.exp(1j * self.rotation))

    def to_dict(self):
        return {"kind": self.kind, "path": self.path, "pos": [self.pos.real, self.pos.imag],
                "rotation": self.rotation, "scale": self.scale, "opacity": self.opacity, "visible": self.visible,
                "locked": self.locked, "units_override": self.units_override,
                "hidden_layers": list(self.hidden_layers)}

    @staticmethod
    def from_dict(d):
        return Underlay(kind=d["kind"], path=d["path"], pos=complex(*d.get("pos", (0, 0))),
                        rotation=d.get("rotation", 0.0), scale=d.get("scale", 1.0), opacity=d.get("opacity", 0.6),
                        visible=d.get("visible", True), locked=d.get("locked", False),
                        units_override=d.get("units_override"), hidden_layers=d.get("hidden_layers", []))


class UnderlayManager(QtCore.QObject):
    """Owns the underlays, their canvas items, and their snap geometry."""

    changed = QtCore.Signal()

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.underlays = []
        self.items = {}  # id(underlay) -> list of graphics items
        self.geometry = {}  # id(underlay) -> DxfGeometry
        self.images = {}  # id(underlay) -> numpy RGBA array
        self.selected = None

    # --- loading ---------------------------------------------------------
    def add(self, u, select=True):
        try:
            if u.kind == "image":
                self.images[id(u)] = _load_image(u.path)
            else:
                self.geometry[id(u)] = load_dxf(u.path, u.units_override)
        except Exception as exc:  # unreadable or missing file
            u.missing = True
            crashlog.breadcrumb(f"underlay load failed {u.path}: {exc}")
        self.underlays.append(u)
        if select:
            self.selected = u
        self.rebuild(u)
        self.changed.emit()
        return u

    def remove(self, u):
        self._clear_items(u)
        self.underlays.remove(u)
        self.geometry.pop(id(u), None)
        self.images.pop(id(u), None)
        if self.selected is u:
            self.selected = self.underlays[-1] if self.underlays else None
        self.changed.emit()

    def clear(self):
        for u in list(self.underlays):
            self.remove(u)

    def reload_units(self, u, units_override):
        u.units_override = units_override
        try:
            self.geometry[id(u)] = load_dxf(u.path, units_override)
        except Exception:
            u.missing = True
        self.rebuild(u)
        self.changed.emit()

    # --- drawing ---------------------------------------------------------
    def _clear_items(self, u):
        for it in self.items.pop(id(u), []):
            self.view.removeItem(it)

    def rebuild_all(self):
        for u in self.underlays:
            self.rebuild(u)

    def rebuild(self, u):
        self._clear_items(u)
        items = []
        f = self.view.factor
        if u.missing:
            self.items[id(u)] = items
            return
        if u.kind == "image":
            arr = self.images[id(u)]
            img = pg.ImageItem(arr, axisOrder="row-major")
            h = arr.shape[0]
            s = u.scale / f
            tr = QtGui.QTransform()
            tr.translate(u.pos.real / f, u.pos.imag / f)
            tr.rotateRadians(u.rotation)
            tr.scale(s, -s)  # image rows run downwards
            tr.translate(0, -h)  # local origin = bottom-left corner of the image
            img.setTransform(tr)
            items.append(img)
        else:
            g = self.geometry[id(u)]
            pen = pg.mkPen(DXF_COLOR, width=1.2)
            for layer in g.layers:
                if layer in u.hidden_layers:
                    continue
                parts = [np.append(u.world(e.points), np.nan) for e in g.entities if e.layer == layer]
                if not parts:
                    continue
                z = np.concatenate(parts) / f
                items.append(pg.PlotDataItem(z.real, z.imag, pen=pen, connect="finite"))
        for it in items:
            it.setZValue(-20)
            it.setOpacity(u.opacity)
            it.setVisible(u.visible)
            self.view.addItem(it)
        self.items[id(u)] = items

    # --- geometry queries -----------------------------------------------
    def snap_points(self):
        pts = []
        for u in self.underlays:
            g = self.geometry.get(id(u))
            if g is None or not u.visible or u.missing or not len(g.snaps):
                continue
            pts.extend(u.world(g.snaps))
        return pts

    def entity_at(self, p, tol):
        """(underlay, entity, world points) of the DXF entity nearest to p."""
        best = None
        for u in self.underlays:
            g = self.geometry.get(id(u))
            if g is None or not u.visible or u.missing:
                continue
            for e in g.entities:
                if e.layer in u.hidden_layers:
                    continue
                w = u.world(e.points)
                d = distance_to_polyline(p, w)
                if d <= tol and (best is None or d < best[0]):
                    best = (d, u, e, w)
        return None if best is None else best[1:]

    def to_dicts(self):
        return [u.to_dict() for u in self.underlays]


def _load_image(path):
    img = QtGui.QImage(str(path))
    if img.isNull():
        raise OSError(f"cannot read image {path}")
    img = img.convertToFormat(QtGui.QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8, count=img.sizeInBytes())
    return arr.reshape(h, img.bytesPerLine() // 4, 4)[:, :w].copy()


# --------------------------------------------------------------------------
class TwoPointTool(Tool):
    """Base for tools that act on the selected underlay with two clicks."""

    cursor = QtCore.Qt.CrossCursor

    def __init__(self, ctx, manager):
        super().__init__(ctx)
        self.m = manager
        self.a = None

    def activate(self):
        self.a = None
        super().activate()

    def hover(self, p):
        r = self.ctx.snap(p, ref=self.a)
        self.ctx.layer.show_snap(r)
        if self.a is not None:
            self.ctx.layer.show_preview(line=[self.a, r.point], points=[self.a])

    def click(self, p, ev):
        q = self.ctx.snap(p, ref=self.a).point
        if self.a is None:
            self.a = q
            self.ctx.layer.show_preview(points=[q])
            return True
        a, self.a = self.a, None
        self.ctx.layer.clear_feedback()
        if abs(q - a) > 0:
            self.apply(a, q)
        self.ctx.w.set_tool("select")
        return True


class CalibrateTool(TwoPointTool):
    name = "calibrate"
    prompt = "Calibrate: click two points on the underlay whose real distance you know"

    def apply(self, a, b):
        u = self.m.selected
        text, ok = QtWidgets.QInputDialog.getText(
            self.ctx.w, "Calibrate underlay",
            f"Real distance between the two points (e.g. 250, 10in):\n"
            f"currently {format_length(abs(b - a), self.ctx.unit)} {self.ctx.unit}")
        if not ok:
            return
        try:
            real = parse_length(text, self.ctx.unit)
        except ValueError:
            QtWidgets.QMessageBox.warning(self.ctx.w, "Calibrate", f"Could not read '{text}'.")
            return
        if real <= 0:
            return
        k = real / abs(b - a)
        # Scale about point a so it stays put.
        la = u.local(a)
        u.scale *= k
        u.pos = a - la * u.scale * np.exp(1j * u.rotation)
        crashlog.breadcrumb(f"calibrate underlay {u.name} x{k:.4f}")
        self.m.rebuild(u)
        self.m.changed.emit()


class AlignTool(TwoPointTool):
    name = "align"
    prompt = "Align: click two points on the underlay that should lie on a horizontal line"

    def apply(self, a, b):
        u = self.m.selected
        d = -cmath.phase(b - a)
        if abs(d) > math.pi / 2:  # keep the drawing's orientation, only level it
            d += math.pi if d < 0 else -math.pi
        la = u.local(a)
        u.rotation += d
        u.pos = a - la * u.scale * np.exp(1j * u.rotation)
        crashlog.breadcrumb(f"align underlay {u.name} by {math.degrees(d):.2f} deg")
        self.m.rebuild(u)
        self.m.changed.emit()


class PickTool(Tool):
    """Click DXF geometry and turn it into a body, path curve or pivot zone."""

    name = "pick"
    prompt = "Use DXF geometry: click a line, arc or polyline in a DXF underlay"
    cursor = QtCore.Qt.PointingHandCursor

    def __init__(self, ctx, manager):
        super().__init__(ctx)
        self.m = manager

    def choose(self, menu):
        """Show the action menu at the cursor (replaced in tests)."""
        return menu.exec(QtGui.QCursor.pos())

    def hover(self, p):
        hit = self.m.entity_at(p, SNAP_PX * self.ctx.layer.mm_per_px())
        self.ctx.layer.show_preview(line=hit[2] if hit else None)

    def click(self, p, ev):
        hit = self.m.entity_at(p, SNAP_PX * self.ctx.layer.mm_per_px())
        if hit is None:
            return True
        u, e, w = hit
        menu = QtWidgets.QMenu(self.ctx.w)
        a_body = menu.addAction("Use as body outline (replace)")
        a_add = menu.addAction("Add to body outline")
        a_path = menu.addAction("Use as target path curve")
        a_zone = menu.addAction("Use as allowed pivot zone")
        a_keep = menu.addAction("Use as keep-out zone")
        for a in (a_zone, a_keep):
            a.setEnabled(len(w) >= 3)
        chosen = self.choose(menu)
        self.ctx.layer.clear_feedback()
        if chosen is None:
            return True
        pts = list(w[:-1] if e.closed else w)
        doc = self.ctx.doc
        if chosen in (a_body, a_add):
            def fn(t):
                if t.keyframes:
                    ref = t.keyframes[0]
                else:
                    ref = Keyframe(pos=complex(np.mean(pts)), angle=0.0)
                    t.keyframes.append(ref)
                local = list(pose_inverse(pts, ref.pos, ref.angle))
                if chosen is a_add and t.body is not None:
                    t.body.polylines.append(local)
                else:
                    t.body = Body([local], closed=e.closed)
            doc.edit("Body from DXF", fn)
        elif chosen is a_path:
            ctrl = list(simplify(np.array(pts), 0.01 * max(1.0, float(np.ptp(np.abs(pts))))))
            if e.closed and len(ctrl) > 3 and abs(ctrl[-1] - ctrl[0]) < 1e-6:
                ctrl = ctrl[:-1]
            c = Curve(points=ctrl, closed=e.closed)
            doc.edit("Path from DXF", lambda t: (t.curves.append(c), setattr(t, "mode", "path")))
        else:
            z = Zone(polygon=pts, allow=chosen is a_zone)
            doc.edit("Zone from DXF", lambda t: t.zones.append(z))
        crashlog.breadcrumb(f"use DXF {e.kind} from {u.name}")
        return True


# --------------------------------------------------------------------------
class LayersPanel(QtWidgets.QWidget):
    """Lists underlays and edits the selected one's placement and display."""

    def __init__(self, window, manager):
        super().__init__()
        self.w, self.m = window, manager
        self.unit = "mm"
        self._updating = False
        lay = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        for label, tip, fn in (("Add image…", "Trace over a photo or scan (PNG, JPG)", self.add_image),
                               ("Add DXF…", "Trace over and snap to a CAD drawing", self.add_dxf),
                               ("Remove", "Remove the selected underlay", self.remove)):
            b = QtWidgets.QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.list = QtWidgets.QListWidget()
        self.list.setMaximumHeight(120)
        self.list.currentRowChanged.connect(self._on_row)
        self.list.itemChanged.connect(self._on_check)
        lay.addWidget(self.list)

        self.props = QtWidgets.QGroupBox("Placement")
        form = QtWidgets.QFormLayout(self.props)
        self.f_x = ValueField("length", self.unit)
        self.f_y = ValueField("length", self.unit)
        self.f_rot = ValueField("angle", self.unit)
        self.f_scale = QtWidgets.QLineEdit()
        self.scale_label = QtWidgets.QLabel("Scale")
        xy = QtWidgets.QWidget()
        xl = QtWidgets.QHBoxLayout(xy)
        xl.setContentsMargins(0, 0, 0, 0)
        for lbl, f in (("x", self.f_x), ("y", self.f_y)):
            xl.addWidget(QtWidgets.QLabel(lbl))
            xl.addWidget(f, 1)
        form.addRow("Origin", xy)
        form.addRow("Rotation", self.f_rot)
        form.addRow(self.scale_label, self.f_scale)
        self.opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity.setRange(5, 100)
        form.addRow("Opacity", self.opacity)
        self.locked = QtWidgets.QCheckBox("Locked (placement fields disabled)")
        form.addRow(self.locked)
        self.units = QtWidgets.QComboBox()
        self.units.addItem("From file", None)
        for name, mm in (("mm", 1.0), ("cm", 10.0), ("m", 1000.0), ("in", 25.4), ("ft", 304.8)):
            self.units.addItem(name, mm)
        self.units_row_label = QtWidgets.QLabel("Drawing units")
        form.addRow(self.units_row_label, self.units)
        tools = QtWidgets.QHBoxLayout()
        self.b_cal = QtWidgets.QPushButton("Calibrate scale")
        self.b_cal.setToolTip("Click two points with a known distance, then type the real distance")
        self.b_cal.clicked.connect(lambda: self.w.set_tool("calibrate"))
        self.b_align = QtWidgets.QPushButton("Align level")
        self.b_align.setToolTip("Click two points that should be horizontal (straightens a tilted photo)")
        self.b_align.clicked.connect(lambda: self.w.set_tool("align"))
        tools.addWidget(self.b_cal)
        tools.addWidget(self.b_align)
        form.addRow(tools)
        self.b_pick = QtWidgets.QPushButton("Use DXF geometry as body / path / zone…")
        self.b_pick.clicked.connect(lambda: self.w.set_tool("pick"))
        form.addRow(self.b_pick)
        lay.addWidget(self.props)

        self.layers_box = QtWidgets.QGroupBox("DXF layers")
        ll = QtWidgets.QVBoxLayout(self.layers_box)
        self.layer_list = QtWidgets.QListWidget()
        self.layer_list.itemChanged.connect(self._on_layer_check)
        ll.addWidget(self.layer_list)
        self.info = QtWidgets.QLabel()
        self.info.setWordWrap(True)
        ll.addWidget(self.info)
        lay.addWidget(self.layers_box, 1)

        self.f_x.committed.connect(lambda v: self._set_pos(complex(v, self.m.selected.pos.imag)))
        self.f_y.committed.connect(lambda v: self._set_pos(complex(self.m.selected.pos.real, v)))
        self.f_rot.committed.connect(lambda v: self._set("rotation", v))
        self.f_scale.editingFinished.connect(self._on_scale)
        self.opacity.valueChanged.connect(lambda v: self._set("opacity", v / 100.0))
        self.locked.toggled.connect(lambda on: self._set("locked", on))
        self.units.activated.connect(lambda _: self.m.selected and self.m.reload_units(self.m.selected,
                                                                                         self.units.currentData()))
        manager.changed.connect(self.refresh)
        self.refresh()

    # --- actions ---------------------------------------------------------
    def add_image(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Add image underlay", "",
                                                        "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.add_file(path)

    def add_dxf(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Add DXF underlay", "", "DXF drawings (*.dxf)")
        if path:
            self.add_file(path)

    def add_file(self, path):
        kind = "dxf" if path.lower().endswith(".dxf") else "image"
        u = Underlay(kind=kind, path=path)
        if kind == "image":
            # Start at about the size of the current view: 0.5 of its width.
            vb = self.w.view.getViewBox()
            (x0, x1), _ = vb.viewRange()
            img = QtGui.QImageReader(path).size()
            if img.width() > 0:
                u.scale = 0.5 * (x1 - x0) * self.w.view.factor / img.width()
                u.pos = complex(x0 * self.w.view.factor, vb.viewRange()[1][0] * self.w.view.factor)
        crashlog.breadcrumb(f"add {kind} underlay {path}")
        self.m.add(u)
        if u.missing:
            QtWidgets.QMessageBox.warning(self, "Underlay", f"Could not read {path}.")
            return
        g = self.m.geometry.get(id(u))
        if g is not None and not g.unit_known:
            self.w.statusBar().showMessage(f"{u.name}: the DXF does not say its units; assuming mm "
                                           "(change 'Drawing units' if that is wrong)", 8000)
        self.w.mark_dirty()
        self.w.view.autoRange()

    def remove(self):
        if self.m.selected:
            self.m.remove(self.m.selected)
            self.w.mark_dirty()

    # --- edits -----------------------------------------------------------
    def _set(self, attr, value):
        u = self.m.selected
        if u is None or self._updating:
            return
        setattr(u, attr, value)
        if attr == "opacity":
            for it in self.m.items.get(id(u), []):
                it.setOpacity(value)
        else:
            self.m.rebuild(u)
        self.w.mark_dirty()
        if attr != "opacity":
            self.refresh()

    def _set_pos(self, pos):
        self._set("pos", pos)

    def _on_scale(self):
        u = self.m.selected
        if u is None or self._updating:
            return
        try:
            v = float(self.f_scale.text())
        except ValueError:
            self.refresh()
            return
        if u.kind == "image":
            v = parse_length(self.f_scale.text(), self.unit)  # mm per pixel
        if v > 0:
            self._set("scale", v)

    def _on_row(self, row):
        if not self._updating and 0 <= row < len(self.m.underlays):
            self.m.selected = self.m.underlays[row]
            self.refresh()

    def _on_check(self, item):
        if self._updating:
            return
        u = self.m.underlays[self.list.row(item)]
        u.visible = item.checkState() == QtCore.Qt.Checked
        for it in self.m.items.get(id(u), []):
            it.setVisible(u.visible)
        self.w.mark_dirty()

    def _on_layer_check(self, item):
        u = self.m.selected
        if self._updating or u is None:
            return
        name = item.text()
        hidden = set(u.hidden_layers)
        (hidden.discard if item.checkState() == QtCore.Qt.Checked else hidden.add)(name)
        u.hidden_layers = sorted(hidden)
        self.m.rebuild(u)
        self.w.mark_dirty()

    # --- display ---------------------------------------------------------
    def set_units(self, unit):
        self.unit = unit
        for f in (self.f_x, self.f_y):
            f.set_unit(unit)
        self.refresh()

    def refresh(self):
        self._updating = True
        self.list.clear()
        for u in self.m.underlays:
            label = f"{'🖼' if u.kind == 'image' else '📐'} {u.name}" + ("  (missing)" if u.missing else "")
            item = QtWidgets.QListWidgetItem(label)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked if u.visible else QtCore.Qt.Unchecked)
            item.setToolTip(u.path)
            self.list.addItem(item)
        u = self.m.selected
        if u in self.m.underlays:
            self.list.setCurrentRow(self.m.underlays.index(u))
        has = u is not None
        self.props.setEnabled(has)
        self.layers_box.setVisible(has and u.kind == "dxf")
        if has:
            editable = not u.locked
            for w in (self.f_x, self.f_y, self.f_rot, self.f_scale, self.b_cal, self.b_align):
                w.setEnabled(editable)
            self.f_x.set_value(u.pos.real)
            self.f_y.set_value(u.pos.imag)
            self.f_rot.set_value(u.rotation)
            if u.kind == "image":
                self.scale_label.setText(f"Pixel size ({self.unit})")
                self.f_scale.setText(format_length(u.scale, self.unit, 6))
            else:
                self.scale_label.setText("Scale factor")
                self.f_scale.setText(f"{u.scale:g}")
            self.opacity.setValue(round(u.opacity * 100))
            self.locked.setChecked(u.locked)
            is_dxf = u.kind == "dxf"
            self.units.setVisible(is_dxf)
            self.units_row_label.setVisible(is_dxf)
            self.b_pick.setVisible(is_dxf)
            if is_dxf:
                idx = self.units.findData(u.units_override) if u.units_override else 0
                self.units.setCurrentIndex(max(0, idx))
                self.layer_list.clear()
                g = self.m.geometry.get(id(u))
                if g is not None:
                    for name in g.layers:
                        it = QtWidgets.QListWidgetItem(name)
                        it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
                        it.setCheckState(QtCore.Qt.Unchecked if name in u.hidden_layers else QtCore.Qt.Checked)
                        self.layer_list.addItem(it)
                    skipped = ", ".join(f"{k} ×{v}" for k, v in sorted(g.skipped.items()))
                    self.info.setText(f"{len(g.entities)} entities · file units: {g.units}"
                                      + ("" if g.unit_known else " (assumed mm)")
                                      + (f"<br>Skipped (not drawn): {skipped}" if skipped else ""))
        self._updating = False
