# kinsyn: notes for Claude

Planar kinematic synthesis desktop app (PySide6 + pyqtgraph + NumPy/SciPy).
Design and roadmap: `PLAN.md`. Run: `.venv/bin/python -m kinsyn`. Tests:
`.venv/bin/pytest`. Headless GUI checks: `QT_QPA_PLATFORM=offscreen`, and set
`XDG_CONFIG_HOME`/`XDG_STATE_HOME` to a scratch dir so the user's settings and
logs are untouched.

- `kinsyn/core/` is GUI-free (mm and radians internally, complex numbers for
  points); `kinsyn/gui/` is the Qt layer; `kinsyn/library/builtin/` holds the
  JSON templates (each has an `expected_class` checked by the tests).

## Docs

Every user-facing feature needs help. That means:
- a tooltip;
- where a term is involved, an entry in `kinsyn/help/topics.py` (`TERMS`);
- a Markdown article or tutorial section in `kinsyn/help/docs/` (add it to
  `TOC`).

Regenerate the diagrams with `tools/make_diagrams.py` and the screenshots
with `tools/make_screenshots.py` (offscreen, with scratch XDG dirs).
`tests/test_help.py` checks links, images and topics. The audience is
**not** experts, so explain terms plainly.

## When kinsyn crashes

Always use the **diagnose-crash** skill, and read kinsyn's own diagnostics,
which the core dump alone does not contain:

- `~/.local/state/kinsyn/faulthandler.log`: Python stack of every thread at
  a native crash (SIGSEGV/SIGABRT/...), written by `faulthandler`
- `~/.local/state/kinsyn/breadcrumbs.log`: the user's recent actions
- `~/.local/state/kinsyn/errors.log`: unhandled Python exceptions, Qt warnings

Match the session by pid/timestamp (each session writes a header line). Fix
the app code where the evidence points to it, and add a breadcrumb or test
if something was missing for the diagnosis.

Known issue: dragging dock panels on Wayland crashed in Qt's drag loop
(double free, 2026-09-29). Panels are therefore locked by default
(View > Unlock panel layout).
