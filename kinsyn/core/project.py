"""Project files (.kinsyn, JSON): target + current mechanism + settings."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from .mechanism import Mechanism
from .target import Target

FORMAT_VERSION = 1


@dataclass
class Project:
    target: Target = field(default_factory=Target)
    mechanism: Mechanism | None = None
    operating_range: tuple | None = None
    units: str = "mm"
    underlays: list = field(default_factory=list)  # dicts, see gui.underlays

    def to_dict(self):
        return {
            "format": "kinsyn-project", "version": FORMAT_VERSION, "units": self.units,
            "target": self.target.to_dict(),
            "mechanism": self.mechanism.to_dict() if self.mechanism else None,
            "operating_range": list(self.operating_range) if self.operating_range else None,
            "underlays": self.underlays,
        }

    @staticmethod
    def from_dict(d):
        import kinsyn.core.families  # noqa: F401  (registers mechanism types)

        if d.get("format") != "kinsyn-project":
            raise ValueError("not a kinsyn project file")
        if d.get("version", 1) > FORMAT_VERSION:
            raise ValueError("project was saved by a newer version of kinsyn")
        op = d.get("operating_range")
        return Project(target=Target.from_dict(d.get("target", {})),
                       mechanism=Mechanism.from_dict(d["mechanism"]) if d.get("mechanism") else None,
                       operating_range=tuple(op) if op else None, units=d.get("units", "mm"),
                       underlays=d.get("underlays", []))


def save_project(project: Project, path):
    Path(path).write_text(json.dumps(project.to_dict(), indent=1) + "\n")


def load_project(path) -> Project:
    return Project.from_dict(json.loads(Path(path).read_text()))
