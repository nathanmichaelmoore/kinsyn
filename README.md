# kinsyn

Planar kinematic synthesis: design four-bar and slider linkages that produce
a motion you specify (motion, path and function generation).

Status: **milestone 1**. Core analysis for four-bars and all slider families,
a mechanism library (including over-center / toggle templates), and a viewer.
See [PLAN.md](PLAN.md) for the full design and roadmap.

## Setup

```sh
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m kinsyn      # launch the GUI
.venv/bin/pytest                # run the tests
```

## Layout

- `kinsyn/core/` — mechanism model, closed-form position solutions, analysis
  (input ranges, circuits, Grashof, transmission angle, toggles), units
- `kinsyn/library/` — built-in mechanism templates (JSON) and the catalog
- `kinsyn/gui/` — PySide6 + pyqtgraph desktop app
- `tests/`
