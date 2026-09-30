"""Mechanism base class, result containers and the type registry.

Conventions: points are complex numbers (x + iy) in mm, angles in radians.
All solvers are vectorised over the input value `q`; configurations that
cannot assemble come back as NaN with `ok == False`.
"""

from dataclasses import dataclass, field, fields, replace
from typing import ClassVar

import numpy as np


@dataclass(frozen=True)
class Param:
    name: str
    label: str
    # length | signed_length | angle | point | branch | choice
    kind: str
    choices: tuple = ()
    help: str = ""


@dataclass
class Frames:
    """Solved configurations for an array of input values."""
    q: np.ndarray
    points: dict  # name -> complex array; "dir:*" keys hold unit direction vectors
    mu: np.ndarray  # transmission angle (rad, NaN when not meaningful)
    output: np.ndarray  # output angle (rad) or displacement (mm)
    ok: np.ndarray

    def __len__(self):
        return len(self.q)

    @staticmethod
    def select(a, b, take_b):
        """Per-sample pick between two solutions (used for branch tracking)."""
        pick = lambda x, y: np.where(take_b, y, x)
        return Frames(q=a.q, points={k: pick(a.points[k], b.points[k]) for k in a.points},
                      mu=pick(a.mu, b.mu), output=pick(a.output, b.output),
                      ok=pick(a.ok, b.ok))


@dataclass
class Drawing:
    """Backend-independent description of how to draw a mechanism."""
    links: list  # tuples of point keys; 3+ keys = rigid plate drawn as polygon
    ground: list  # point keys of ground pivots
    pins: list  # point keys of moving revolute joints
    blocks: list = field(default_factory=list)  # (point key, "dir:*" key or fixed angle)
    rails: list = field(default_factory=list)  # (point on rail, angle, half length) - static
    coupler: tuple = ()  # the link carrying the tracer point (highlighted)
    tracer: str = "P"


def angle_between(u, v):
    """Unsigned angle between direction vectors, in [0, pi]."""
    return np.abs(np.angle(v * np.conj(u)))


class Mechanism:
    kind: ClassVar[str]
    title: ClassVar[str]
    params: ClassVar[tuple]

    # --- to implement in subclasses -------------------------------------
    def solve(self, q, branch=None) -> Frames:
        raise NotImplementedError

    def input_domain(self):
        """(lo, hi, periodic) range to search for assemblable inputs."""
        raise NotImplementedError

    def drawing(self) -> Drawing:
        raise NotImplementedError

    def classify(self):
        """(class name, list of notes)."""
        raise NotImplementedError

    @property
    def input_kind(self):  # "angle" or "length"
        return "angle"

    @property
    def output_kind(self):
        return "angle"

    @property
    def output_label(self):
        return "Output"

    @property
    def has_branches(self):
        return True

    def scale(self):
        """Characteristic size (mm), for drawing and tolerances."""
        raise NotImplementedError

    def toggle_links(self):
        """(fixed point key, joint key, far key) whose collinearity is the
        toggle / over-center condition (input link aligned with coupler)."""
        return None

    # --- shared ----------------------------------------------------------
    def copy(self, **changes):
        return replace(self, **changes)

    def to_dict(self):
        kinds = {p.name: p.kind for p in self.params}
        d = {"type": self.kind}
        for f in fields(self):
            v = getattr(self, f.name)
            d[f.name] = [v.real, v.imag] if kinds.get(f.name) == "point" else v
        return d

    @staticmethod
    def from_dict(d):
        cls = REGISTRY[d["type"]]
        kinds = {p.name: p.kind for p in cls.params}
        kw = {}
        for f in fields(cls):
            if f.name not in d:
                continue
            v = d[f.name]
            kw[f.name] = complex(v[0], v[1]) if kinds.get(f.name) == "point" else v
        return cls(**kw)


REGISTRY: dict = {}


def register(cls):
    REGISTRY[cls.kind] = cls
    return cls
