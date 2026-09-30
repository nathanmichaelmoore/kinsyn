# kinsyn

Planar kinematic synthesis: design four-bar and slider linkages that produce
a motion you specify (motion, path and function generation).

Status: **milestones 1–2 done**.

- **Analysis:** four-bars and all the slider families, with Grashof class,
  transmission angle, toggles and over-center, velocity, acceleration and
  mechanical advantage.
- **Mechanism library:** ready-made templates to learn from and start with.
- **Target editor:** poses, ghost bodies, curves, pivot zones and fixed
  pivots, snapping, typed coordinates, a timeline, and image / DXF
  underlays.
- **Built-in help (F1):** tutorials, concept articles and reference pages.

Next up: motion generation, the solvers that turn your poses into linkages.
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
- `kinsyn/help/` — help window, topic registry and the Markdown docs
- `tools/` — `make_diagrams.py` (concept SVGs from the real geometry code) and
  `make_screenshots.py` (app screenshots for the docs)
- `tests/`
