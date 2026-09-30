"""DXF import for underlays: flatten supported entities to polylines in mm,
and collect snap points (endpoints, midpoints, centres, vertices, line
intersections)."""

from dataclasses import dataclass, field

import numpy as np

# $INSUNITS code -> mm per drawing unit (0 = unitless)
INSUNITS_MM = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 8: 25.4e-6, 9: 0.0254, 10: 914.4}
INSUNITS_NAME = {0: "unitless", 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m", 8: "µin", 9: "mil", 10: "yd"}
SUPPORTED = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE"}
MAX_INTERSECT_LINES = 1500


@dataclass
class DxfEntity:
    layer: str
    kind: str
    points: np.ndarray  # complex, mm (drawing coordinates scaled to mm)
    closed: bool = False


@dataclass
class DxfGeometry:
    entities: list
    snaps: np.ndarray  # complex, mm
    units: str  # name of the drawing's own unit
    mm_per_unit: float
    unit_known: bool
    skipped: dict = field(default_factory=dict)  # entity type -> count

    @property
    def layers(self):
        return sorted({e.layer for e in self.entities})


def _flatten(entity, tol):
    from ezdxf import path as ezpath
    p = ezpath.make_path(entity)
    pts = np.array([complex(v.x, v.y) for v in p.flattening(tol)])
    return pts


def _walk(entities, out, skipped, depth=0):
    for e in entities:
        t = e.dxftype()
        if t == "INSERT" and depth < 8:
            try:
                _walk(e.virtual_entities(), out, skipped, depth + 1)
            except Exception:  # malformed block reference
                skipped["INSERT"] = skipped.get("INSERT", 0) + 1
        elif t in SUPPORTED:
            out.append(e)
        else:
            skipped[t] = skipped.get(t, 0) + 1


def _segment_intersections(segs):
    """Pairwise intersections of line segments (array of (a, b) complex)."""
    if len(segs) < 2:
        return np.array([], complex)
    a = segs[:, 0][:, None]
    b = segs[:, 1][:, None]
    c = segs[:, 0][None, :]
    d = segs[:, 1][None, :]
    r, s = b - a, d - c
    cross = lambda u, v: (np.conj(u) * v).imag
    den = cross(r, s)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = cross(c - a, s) / den
        u = cross(c - a, r) / den
    ok = (np.abs(den) > 1e-12) & (t >= -1e-9) & (t <= 1 + 1e-9) & (u >= -1e-9) & (u <= 1 + 1e-9)
    ok = np.triu(ok, 1)
    i, j = np.nonzero(ok)
    return (a[:, 0][i] + t[i, j] * r[:, 0][i])


def load_dxf(path, units_override=None, flatten_tol=0.05):
    """Read a DXF. `units_override` is mm per drawing unit (None = use the
    file's $INSUNITS; unitless files are assumed to be mm)."""
    import ezdxf

    doc = ezdxf.readfile(str(path))
    code = int(doc.header.get("$INSUNITS", 0) or 0)
    known = code in INSUNITS_MM
    scale = units_override or INSUNITS_MM.get(code, 1.0)
    raw, skipped = [], {}
    _walk(doc.modelspace(), raw, skipped)

    entities, snaps, segs = [], [], []
    for e in raw:
        t = e.dxftype()
        try:
            pts = _flatten(e, flatten_tol / scale if scale else flatten_tol) * scale
        except Exception:
            skipped[t] = skipped.get(t, 0) + 1
            continue
        if len(pts) < 2:
            continue
        closed = bool(abs(pts[-1] - pts[0]) < 1e-9 * max(1.0, np.abs(pts).max()))
        entities.append(DxfEntity(e.dxf.layer, t, pts, closed))
        if t == "LINE":
            a, b = pts[0], pts[-1]
            snaps += [a, b, (a + b) / 2]
            segs.append((a, b))
        elif t in ("ARC", "CIRCLE", "ELLIPSE"):
            snaps.append(complex(e.dxf.center.x, e.dxf.center.y) * scale)
            if t != "CIRCLE":
                snaps += [pts[0], pts[-1]]
        elif t in ("LWPOLYLINE", "POLYLINE"):
            verts = [complex(v[0], v[1]) for v in (e.get_points("xy") if t == "LWPOLYLINE" else
                                                    [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices])]
            snaps += [v * scale for v in verts]
        else:
            snaps += [pts[0], pts[-1]]
    if 1 < len(segs) <= MAX_INTERSECT_LINES:
        snaps += list(_segment_intersections(np.array(segs)))
    return DxfGeometry(entities, np.array(snaps, complex), INSUNITS_NAME.get(code, f"code {code}"),
                       scale, known or units_override is not None, skipped)


def distance_to_polyline(p, pts):
    """Shortest distance from point p to a polyline."""
    a, b = pts[:-1], pts[1:]
    ab = b - a
    L2 = np.abs(ab) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.clip(np.where(L2 > 0, ((p - a) * np.conj(ab)).real / L2, 0.0), 0, 1)
    return float(np.min(np.abs(a + t * ab - p))) if len(a) else float(abs(pts[0] - p))
