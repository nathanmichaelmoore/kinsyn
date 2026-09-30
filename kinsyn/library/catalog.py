"""Mechanism library: built-in (read-only) and user entries, one JSON file each."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from kinsyn.core.mechanism import Mechanism

BUILTIN_DIR = Path(__file__).parent / "builtin"
USER_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "kinsyn/library"

GROUP_ORDER = ["Grashof classes", "Slider families", "Over-center / toggle", "My designs"]


@dataclass
class Entry:
    id: str
    name: str
    group: str
    description: str
    mechanism: Mechanism
    tags: list = field(default_factory=list)
    operating_range: tuple | None = None  # input units: rad or mm
    expected_class: str | None = None
    builtin: bool = True
    path: Path | None = None

    def matches(self, text):
        text = text.lower().strip()
        if not text:
            return True
        hay = " ".join([self.name, self.group, self.description, *self.tags]).lower()
        return all(word in hay for word in text.split())

    def to_dict(self):
        d = {"id": self.id, "name": self.name, "group": self.group, "tags": list(self.tags),
             "description": self.description, "mechanism": self.mechanism.to_dict()}
        if self.operating_range:
            d["operating_range"] = list(self.operating_range)
        if self.expected_class:
            d["expected_class"] = self.expected_class
        return d


def load_entry(path: Path, builtin: bool) -> Entry:
    d = json.loads(path.read_text())
    op = d.get("operating_range")
    return Entry(id=d["id"], name=d["name"], group=d.get("group", "My designs"),
                 description=d.get("description", ""), tags=d.get("tags", []),
                 mechanism=Mechanism.from_dict(d["mechanism"]),
                 operating_range=tuple(op) if op else None,
                 expected_class=d.get("expected_class"), builtin=builtin, path=path)


def load_all(user_dir: Path = USER_DIR) -> list[Entry]:
    """Built-in entries first, then user entries. Unreadable user files are skipped."""
    import kinsyn.core.families  # noqa: F401  (registers mechanism types)

    entries = [load_entry(p, True) for p in sorted(BUILTIN_DIR.glob("*.json"))]
    if user_dir.is_dir():
        for p in sorted(user_dir.glob("*.json")):
            try:
                entries.append(load_entry(p, False))
            except (ValueError, KeyError, TypeError):
                continue
    return entries


def save_user_entry(entry: Entry, user_dir: Path = USER_DIR) -> Path:
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{entry.id}.json"
    path.write_text(json.dumps(entry.to_dict(), indent=2) + "\n")
    return path
