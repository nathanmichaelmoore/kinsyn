# Planar Kinematic Synthesis Tool — Plan

A desktop app for kinematic synthesis of planar single-loop linkages. You
specify the motion you want, it generates candidate mechanisms that
produce it, ranks them, and lets you inspect, animate, and export them.

## Scope

- **Mechanism families:** all single-loop, one-input linkages built from
  pin (R) and slider (P) joints:
  - four-bar (RRRR)
  - slider-crank (RRRP)
  - inverted slider-cranks (RRPR, RPRR)
  - double-slider cases such as the elliptical trammel and Scotch yoke
- **Out of scope for now:** five-bars and other multi-loop linkages. The
  core should still not rule them out later.

## Decisions so far

| Decision | Choice |
|---|---|
| Scope | General planar kinematic synthesis; four-bar and slider families; no five-bars |
| Joints | Pin (revolute) and slider (prismatic) supported from the start |
| Synthesis types | Motion generation, path generation, function generation (all three) |
| Platform | Python desktop app: PySide6 (Qt) + NumPy/SciPy + pyqtgraph |
| Primary input | Draw/drag targets on a canvas, with numeric fields to fine-tune values |
| Purpose | Real design work: units, quality checks, and CAD export |

## Architecture

The math core has no GUI dependency. The GUI is a thin layer on top of it,
so every solver can be unit-tested and scripted on its own.

```
kinsyn/
  core/
    joints.py         # RevoluteJoint, PrismaticJoint (slider axis, offset)
    mechanism.py      # single-loop mechanism: ordered links + joints; FourBar and
                      # SliderCrank are named presets built on it
    analysis.py       # position solve (both assembly branches) for each R/P
                      # combination, coupler curve, velocity, transmission angle,
                      # Grashof classification (and its slider-crank equivalent)
    checks.py         # branch, order, and circuit defects; transmission angle limits;
                      # pivot keep-in/keep-out regions; link length and stroke limits
    target.py         # Target / Keyframe / Body / curve segments / pivot zones
  synthesis/
    dyad.py           # RR dyad in complex standard form: W(e^{iβj}-1) + Z(e^{iαj}-1) = δj
                      # plus RP/PR dyads (slider on ground or on the coupler)
    motion.py         # 2, 3, 4, and 5 precision-position (Burmester) motion generation
    burmester.py      # center-point and circle-point curves, Burmester points
    path.py           # path generation by optimization (with or without prescribed timing)
    function.py       # Freudenstein function generation, Chebyshev spacing
    ranking.py        # score and filter candidate linkages
  library/
    builtin/          # read-only JSON entries shipped with the app
    catalog.py        # load/search/filter entries (built-in + user)
    atlas.py          # generate + query the coupler-curve atlas (Fourier descriptors)
  io/
    project.py        # save/load project (.json): targets, constraints, chosen solution
    export.py         # DXF (ezdxf), CSV coupler curve, SVG
  gui/
    main_window.py    # mode tabs: Motion / Path / Function / Analyze
    canvas.py         # pyqtgraph scene: draggable poses, sketched paths, animated linkage
    tools.py          # pose/point/curve/body/zone/pivot/measure tools, typed input
    snapping.py       # grid, angle, object snaps, alignment guides
    underlays.py      # image + DXF underlays, calibration, layers panel
    timeline.py       # keyframe timing strip + playhead
    commands.py       # QUndoCommand subclasses for every edit
    library_panel.py  # browse library + atlas, previews, sliders, "use as template"
    solutions.py      # sortable table of candidate linkages
    plots.py          # transmission angle, output angle, and velocity vs. crank angle
tests/
```

## Specifying the desired motion

### One data model: the target
All three modes are driven by one **target**: an ordered list of
**keyframes**, plus (optionally) curve segments between them.

| Keyframe field | Motion gen | Path gen | Function gen |
|---|---|---|---|
| Position x, y | required | required | n/a |
| Orientation θ | required | ignored | n/a |
| Input angle θ_in or time t | optional | optional | required |
| Output value (angle or slider stroke) | n/a | n/a | required |
| Tolerance (± distance, ± angle) | optional | optional | optional |
| Weight | optional | optional | optional |

- **Order matters.** Keyframes are numbered, and the mechanism must pass
  through them in that sequence (this is what the order-defect check
  enforces). Reorder by dragging in the list.
- **Exact vs. approximate.** A keyframe with zero tolerance is a precision
  point, meaning it must be hit exactly. With a tolerance, it's a region
  the mechanism only has to pass inside.
- **The app picks the solver from the target** and tells you which it
  chose. The status bar shows the result, for example:
  - "3 exact poses → dyad solve"
  - "5 exact poses → Burmester points"
  - "9 poses with tolerance → optimizer"

### Canvas tools

| Tool | Key | What it does |
|---|---|---|
| Select / move | V | Drag keyframes, handles, and curve control points. Box-select several at once. |
| Pose | P | Click to place a pose, then drag to set its angle. |
| Point | O | Click to place path points (position only). |
| Curve | C | Sketch a curve freehand, or click to place spline control points. |
| Body | B | Draw the shape of the part being moved. |
| Pivot zone | Z | Draw rectangles or polygons where ground pivots are allowed, or not allowed. |
| Fixed pivot | F | Pin a ground pivot or slider axis to an exact spot you require. |
| Measure | M | Measure distances and angles. |

- **Poses as ghost bodies (motion generation).** This is the main way to
  set up a motion, and you've confirmed this approach.
  - With the Body tool you draw, or import, the part you want to move: a
    door, a gripper jaw, a flap. This becomes the coupler.
  - Each pose is a semi-transparent copy of that body. It has a move handle
    at a reference point and a rotation handle.
  - Poses are laid out by moving the body around, which matches how you
    picture the motion in your head.
  - If you don't draw a body, each pose shows as a simple arrow instead.
- **Curves (path generation).**
  - A freehand stroke is smoothed into an editable spline with a small
    number of control points, so hand shake is removed and you can adjust
    the result afterwards.
  - Clicked control points give a clean spline directly.
  - Curves can be open or closed.
  - A curve is converted to target points by sampling it evenly along its
    length. Any keyframe you place on the curve pins that point to a
    specific timing.
- **Underlay.** Import an image, DXF, or SVG as a background to trace over,
  such as an existing machine, a photo, or a CAD sketch. Set the scale by
  clicking two points and typing the real distance between them. DXF
  geometry can be snapped to.

### Underlays (image and DXF)
Both kinds live in a **Layers panel**. Each underlay can be shown or
hidden, locked, and has its own opacity, and there can be any number of
them.

- **Image underlays (PNG, JPG)**
  - **Calibrate:** click two points on the image and type the real distance
    between them. This sets the scale.
  - **Align:** click two points that should be horizontal (or at a chosen
    angle) to straighten a photo taken at a tilt.
  - Once calibrated, the image can be moved and rotated, then locked in
    place.
  - Images can't be snapped to, since they are only pixels. For precise
    placement, use a DXF.
- **DXF underlays (via `ezdxf`)**
  - **Imported geometry:** LINE, ARC, CIRCLE, LWPOLYLINE/POLYLINE, SPLINE,
    ELLIPSE, and the contents of blocks (INSERT). Unsupported types are
    skipped, and the import reports which ones.
  - **Units:** taken from the file's `$INSUNITS` setting, with a manual
    override when the file doesn't say.
  - Layers from the DXF appear as sub-items that can be switched on and
    off.
  - **Placement:** an insertion offset and rotation, for when the drawing's
    origin isn't where you want it.
  - **Snapping:** every endpoint, midpoint, center, and intersection can be
    snapped to.
- **Turning underlay geometry into targets.** DXF geometry can be used
  directly, not just traced by hand:
  - **Select → "Use as body":** the selected entities become the ghost-body
    outline, for example the part drawn in your CAD sketch.
  - **Select → "Use as path":** a polyline or spline becomes the target
    curve for path generation.
  - **Select → "Pivot zone":** a closed outline becomes an allowed or
    keep-out region for ground pivots.
- **Saving:** underlays are stored in the project file by path, together
  with their calibration and placement. If a file is missing when the
  project is reopened, the project still opens and shows a warning.

### Snapping
- **Master toggle:** snapping on or off with S. Holding Alt suppresses it
  for a moment.
- **Grid:** adjustable spacing, drawn as major and minor lines. The grid
  adapts as you zoom.
- **Angles:** 15° increments while Shift is held. This applies when setting
  pose angles, placing points relative to the last one, and setting a
  slider axis.
- **Objects:** snaps to keyframes, curve endpoints and midpoints, underlay
  (DXF) endpoints, intersections, and circle centers.
- **Alignment guides:** dashed lines appear when the cursor is horizontally
  or vertically aligned with an existing point, as in CAD programs.
- **Snap indicator:** a small glyph near the cursor shows what it is
  snapping to (grid, endpoint, and so on).

### Exact numeric entry (a precise value is always available)
- **Type while placing.** After the first click, start typing. For
  example, `120, 45` then Tab then `30°` places a pose at (120, 45) with
  θ = 30°. Relative input `@dx, dy` (as in AutoCAD) is also accepted.
- **Inspector panel.** Every selected keyframe shows editable fields: x,
  y, θ, timing, tolerance, and weight. Math expressions are allowed in
  the fields, for example `2*25.4`.
- **Keyframe table.** A spreadsheet-style list of all keyframes that you
  can edit, reorder, and paste into straight from Excel or CSV. The table
  and the canvas are two views of the same data, so a change in either
  shows up in the other.

### Timing: "positions through time"
There is a **timeline strip** under the canvas. It represents one input
cycle: 0–360° of crank rotation for a full-rotation input, or one swing
for a rocking input.
- Each keyframe appears as a marker on the timeline. There are three kinds:
  - **Free timing (hollow marker):** the solver decides when it gets there.
    This is the default, and it makes solutions much easier to find.
  - **Prescribed timing (solid marker):** fixed at a specific input angle.
    Drag it along the strip, or type the value.
  - **Relative timing:** "Δθ_in = 40° after the previous keyframe", for
    when only the spacing between keyframes matters.
- **Units:** input angle in degrees, or time in seconds at a set constant
  input speed (rpm). You can switch between them; the conversion is
  θ = ωt.
- Choosing timing for 3-position motion generation sets the free choices
  (β2, β3) directly. With free timing, the GUI lets you move them and see
  how the solution changes.
- **Scrubbing.** Once a solution is selected, dragging the playhead
  animates the mechanism, so you can see whether each keyframe is hit at
  its marked time.

### Function generation input
This mode uses a separate **θ_in → output plot** instead of the spatial
canvas. There are three ways to define the target:
- Type an equation, such as `y = log10(x)` for x from 1 to 10, and map the
  x and y ranges to input and output angles (or slider stroke).
- Draw the relationship on the plot, with the same curve tools as the
  canvas.
- Type or paste the pairs into the table.

The default precision points use Chebyshev spacing, and you can drag them
along the curve.

### Live feedback while editing
- **Few exact poses (5 or fewer):** re-solved on every drag. The Burmester
  curves, valid pivot regions, and candidate linkages update as you move a
  pose.
- **Optimizer runs:** these are too slow for live updates. They run when
  you press Solve, and while one runs, the current best result draws as a
  faint preview.
- **Warnings on the targets themselves.** Problems show up next to the
  keyframes that cause them, for example:
  - "Poses 2 and 3 are nearly identical → poorly conditioned"
  - "5 exact poses with prescribed timing is over-constrained for a
    four-bar"

## Mechanism library (reference and templates)

The **Library panel** is a browsable catalog of standard mechanisms and
standard motions.
- Every entry has an animated preview you can play or scrub, with its
  coupler curve and moving parts drawn.
- You can use any entry as the starting point for your own design.

### Entry contents
- **Animated preview:** the thumbnail animates on hover. The full view
  shows the mechanism moving, its coupler curve, and its transmission
  angle plot.
- **Description:** what the mechanism is, what it's used for, and its key
  properties, such as:
  - Grashof class
  - whether the input fully rotates
  - swing angle
  - time ratio (quick return)
  - straight-line accuracy or dwell length
- **Live parameter sliders:** change the proportions and watch the motion
  change. The Grashof class and validity update live, so the sliders also
  teach you what each proportion does.
- **Tags** for searching and filtering, such as `straight-line`, `dwell`,
  `quick-return`, `slider`, `crank-rocker`, `parallel-motion`.

### Starting catalog

| Group | Entries |
|---|---|
| **Grashof classes** | crank-rocker; double-crank (drag link); double-rocker; change point; non-Grashof triple-rocker; parallelogram; antiparallelogram; deltoid (kite) |
| **Slider families** | in-line slider-crank (engine/pump); offset slider-crank; inverted slider-crank (oscillating cylinder, hydraulic actuator); Whitworth quick-return; crank-shaper quick-return; Scotch yoke; elliptical trammel; Oldham coupling |
| **Straight-line** | Watt; Chebyshev; Roberts; Hoeken; Chebyshev lambda; Evans |
| **Common motions** | windshield wiper (crank-rocker); pumpjack; toggle clamp (high mechanical advantage near toggle); four-bar door/cabinet hinge; parallel-motion lift (translation without rotation); remote-center rotation; Ackermann steering; film-advance claw (approximate dwell); dwell mechanisms |

### How entries are used as templates
- **Open in Analyze:** load the mechanism as editable. Change dimensions
  numerically or by dragging pivots, and watch the effect.
- **Use its motion as my target:**
  - The entry's coupler curve becomes the target path. Clean it up, scale
    it, and edit it from there.
  - Or pick N positions of its coupler as target poses.
  - Useful for "I want roughly this, but in my space and at my size".
- **Seed the solver:** the entry becomes the starting guess for a path or
  motion optimization. Starting from something close converges much
  faster.
- **Fit to my space:** scale, rotate, and move the entry onto your
  underlay by clicking two reference points.

### Coupler-curve atlas (built on the library)
This is a searchable, generated atlas of coupler curve shapes. It follows
the classic Hrones–Nelson atlas, which mechanism designers use to find a
four-bar that traces a desired shape.
- **Generation:** the atlas is built offline by sweeping link-length
  ratios and coupler point positions for four-bars and slider-cranks.
  Each curve is stored as a normalized Fourier descriptor, which captures
  its shape regardless of size, position, and rotation. A few tens of
  thousands of curves fit in a few MB.
- **Browse:** a grid of curve thumbnails, filtered by features:
  - closed or figure-eight
  - contains a near-straight segment
  - contains a near-circular-arc segment (a dwell)
  - has a cusp
- **Find similar:** draw or select a target curve, and the atlas returns
  the closest shapes. Matching compares Fourier descriptors, so it ignores
  scale, rotation, and position. Each match is fitted onto your curve and
  can then be refined with the path optimizer.
- **Solver seeding:** path generation uses this search by default. The
  best atlas matches become some of the starting points for the global
  search.

### Your own entries
- **Save to library** stores any solution or edited design as a personal
  entry, with a name, notes, and tags.
- **Storage:** built-in entries are shipped with the app and are
  read-only. Personal entries go in `~/.local/share/kinsyn/library/`.
- **Format:** each entry is one small JSON file holding the mechanism
  definition, the ranges for its sliders, a description, and its tags.
  Thumbnails are generated from the geometry, never stored as images.

## Help and learning

Assume users are **not** kinematics experts. Help must always be one click
away, but never in the way: no modal pop-ups and no forced tours.

Help is layered, from lightest to deepest:
1. **Tooltips:** one-line definitions on hover (terms, parameters, plots,
   tools).
2. **"?" links:** on key terms in the analysis summary and on each plot,
   opening the matching article.
3. **Help window (F1):** non-modal and searchable, with three sections:
   - **Tutorials:** step-by-step guides with screenshots and diagrams.
   - **Concepts:** plain-language articles, each covering what it is, why
     it matters, how it appears in kinsyn, and a rule of thumb.
   - **Reference:** tools, shortcuts, and the values you can type into
     fields.
4. **(Later) Guided tutorials:** an optional side panel with a checklist
   that ticks off steps as you actually do them, plus example projects.

How the docs are built and kept correct:
- Docs are Markdown files in `kinsyn/help/docs/`, versioned in the repo.
- Diagrams are generated from the real geometry code by
  `tools/make_diagrams.py`, and screenshots by `tools/make_screenshots.py`,
  so they stay accurate.
- Tests check that every link, image and help topic resolves.

## Over-center (toggle) mechanisms

Over-center locks are a first-class design target, used in toggle clamps,
latches, toggle presses and folding mechanisms.
- **Toggle detection:** a toggle is where the input link and coupler are
  collinear. At that point the output is at a dead point and mechanical
  advantage goes to infinity. Every analysis detects and reports these
  positions, interpolated between samples, and marks them on the coupler
  curve.
- **Operating range:** the input can be limited to a working range, for
  example from an "open" angle to a stop. The circuit, metrics and plots
  then cover only that range.
- **Over-center amount:** if a toggle lies inside the operating range, the
  report shows how far past the toggle the stop sits (typically 2–5°).
  Without one, it notes that the mechanism will not lock.
- **Mechanical advantage:** plotted along the circuit, on a log scale.
- **Library templates:** a four-bar toggle clamp and a slider toggle
  press/latch.
- **Later (synthesis):** "design an over-center clamp" as a target type.
  You specify the open pose, the clamped pose, the over-center angle and
  the handle travel. The solver places the toggle just before the clamped
  pose.

## Validity requirements (enforced, not just reported)

Every candidate from every solver must pass these checks before it
appears in the solutions table. Anything rejected is kept in a
"rejected (why)" list, so you can see what was ruled out and for which
reason.

**Input rotation requirement (a per-project option, default "Any")**

A linkage that fails Grashof is still valid. The input link simply rocks
back and forth instead of fully rotating. So Grashof is a design choice,
not a pass/fail check. The "Input motion" option has these settings:

- **Any (default):** Grashof and non-Grashof linkages are both allowed. For
  a rocking input, the program computes the input's swing range, which is
  the angle between its two toggle positions. It then requires every
  precision position to lie inside that range, all on one side of the
  toggles. That way the motion is reached by rocking, without passing
  through a toggle.
- **Full rotation required:** the input link must be a crank.
  - Four-bar: s + l ≤ p + q (shortest link plus longest link at most the
    sum of the other two), with the shortest link as the input. That gives
    a crank-rocker. If the shortest link is the ground instead, the result
    is a double-crank (drag link).
  - Slider-crank with crank r, coupler L, and offset e: the crank fully
    rotates when L ≥ r + |e|.
  - The inverted slider-cranks each get the equivalent condition for their
    own geometry.
- **Specific Grashof class:** crank-rocker, double-crank, double-rocker, or
  non-Grashof (triple-rocker), for when you want a particular type.

The Grashof class is always calculated and shown in the solutions table,
along with the input's swing range when it rocks. You can sort and filter
on both, whatever the option is set to.

**Hard constraints (on by default, can be relaxed per project)**
- **Change-point (s + l = p + q):** rejected by default. At the change
  point the linkage can flip to the other assembly configuration.
- **Transmission angle:** it must stay within [μ_min, 180° − μ_min] over
  the whole motion that is actually used. The default μ_min is 40°.
- **No branch defect:** all precision positions must be reached on the
  same assembly configuration (open or crossed), without disassembling
  the linkage.
- **No order defect:** the precision positions must be reached in the
  order you specified as the input moves. For a rocking input, this means
  within a single swing between the toggles.
- **Geometry limits:** minimum and maximum link length, maximum length
  ratio, slider stroke limits, and ground pivots inside the allowed
  regions.

**How each solver enforces them**
- **Exact solvers (dyad and Burmester):** generate all the candidates, then
  filter them. On the Burmester curves, the GUI colors the segments by
  whether choosing a pivot there would give a valid linkage. You see the
  usable parts of the curve before you click.
- **Optimizers (path and function generation):** these don't generate and
  then filter. The constraints are built into the search itself, in two
  layers:
  - The parameters are set up so that most invalid designs can't be
    produced. For example, when full rotation is required, the input is
    sampled as the shortest link and the other lengths come from a region
    that already satisfies Grashof. With "Any", the full range of link
    lengths is searched.
  - Any remaining violations (transmission angle, defects, regions) are
    added to the error as penalties. A final hard filter runs at the end.

## The math, per mode

### Analysis (shared foundation, built first)
- Solve the position loop closure analytically for both assembly
  configurations (open and crossed).
- Sweep the crank angle to get the coupler curve, and detect dead points
  where the linkage cannot assemble.
- Classify the linkage by Grashof type (crank-rocker, double-crank,
  double-rocker, change point, triple-rocker).
- Compute the transmission angle over the cycle and report its min and max.
- Slider joints have their own closed-form position solutions. Each
  R/P combination gets its own analytic case, and a generic Newton
  loop-closure solver cross-checks them in the tests.
- Every synthesis result is checked afterwards by re-running analysis on
  it. That round trip also serves as the main correctness test.

### Motion generation (coupler passes through poses x, y, θ)
- **2 positions:** closed form. You choose the free parameters, such as the
  pivot locations.
- **3 positions:** standard-form dyad equations. Choose β2 and β3 (or the
  pivot locations), then solve a linear system. The GUI shows how the
  pivot moves as the free choices change.
- **4 positions:** sweep β2, solve the compatibility equations, and trace the
  **center-point and circle-point curves**. You click a point on the
  center-point curve to pick a ground pivot. Any two picks form a linkage.
- **5 positions:** the Burmester points, which are the intersections of the
  curves (0, 2, or 4 real solutions). Each pair of them gives a linkage.
- **Sliders:** a slider is the limiting case of a pin at infinity.
  - A ground pivot at the far end of the center-point curve becomes a
    slider on ground. Its axis is the direction of that far end.
  - A circle point is replaced by the **Ball point**: a coupler point whose
    precision positions lie on one straight line.
  - As a result, RR and slider dyads come from the same Burmester curves.
    The GUI marks where the curves go to infinity as slider options.
- Afterwards, filter out solutions that have branch or order defects, which
  means they would pass through the poses out of order or on different
  assembly branches. This is where most textbook "solutions" fail in
  practice.

### Path generation (a coupler point traces a curve)
- Input is a sketched curve or N clicked points, with an optional timing
  (crank angle) for each point.
- Exact precision-point synthesis stops being practical beyond about 5
  points, so the default is **optimization**:
  - Global search with `scipy.optimize.differential_evolution` over the
    linkage parameters (4 link lengths, coupler point offset, ground frame).
  - Local refinement with `least_squares`.
  - Error measured as distance from each target point to the coupler curve
    (no timing), or to the point at its specified crank angle (timing).
  - Optionally, an initial shape match using Fourier descriptors of the
    closed curve, which ignores position, rotation, and scale. The best
    match is then scaled and placed onto the target.
- You choose which mechanism families to search. Each family has its own
  set of parameters (a slider-crank uses slider angle and offset instead of
  a fourth pivot).
- Produce a set of diverse solutions rather than only the single best one.

### Function generation (output angle = f(input angle))
- Freudenstein's equation. Three precision points give an exact linear
  solve, with Chebyshev spacing to minimize structural error.
- With more than 3 points, least squares, and a plot of structural error
  over the range.
- Slider-crank version, where slider displacement is a function of crank
  angle. It has its own Freudenstein-style linear form, solved the same way.
- Input is an equation (for example `log(x)` over a range) or a curve you
  draw on the θ₂ → θ₄ plot.

## GUI

- **Canvas, keyframe table, and timeline:** see "Specifying the desired
  motion" above.
- **Solutions panel:** table of candidates with columns for Grashof type,
  minimum transmission angle, defects, link length ratio, and error.
  Selecting a row previews it on the canvas.
- **Live animation:** play or scrub the crank. Shows the coupler curve and
  ghost overlays of the target poses.
- **Numeric inspector:** exact values for every pivot and length, all
  editable. Editing a value re-runs analysis immediately.
- **Plots dock:** transmission angle, output angle, and coupler velocity vs.
  crank angle.
- **Export:** DXF (link centerlines plus pivot circles), coupler curve CSV,
  and project JSON.

## Milestones

Status (2026-10-19): milestones 1, 2 and 3 are done, plus help and docs,
preferences and crash diagnostics. Milestone 4 is next.

Milestone 3 as built (`kinsyn/synthesis/`, Synthesis tab):
- Dyads: pin-pin (from a ground pivot), slider on ground (from a rail
  direction) and swivel (from a slide direction), each a small linear solve.
  Paired into four-bars, slider-cranks (crank or slider input) and inverted
  slider-cranks (crank or cylinder input). The trammel (two sliders) is not
  generated yet.
- Prescribed timing on every pose fixes the input crank (standard-form dyad
  equations). Partial timing is ignored, with a note.
- Every candidate is re-analysed: round trip, branch / order / circuit
  defects, transmission angle between the first and last pose, input-motion
  option, change point, link ratio, zones. Rejected designs keep their reason.
- Live: the picked design is re-solved from the same free choices on every
  edit (and follows dragged fixed pivots); the full search re-runs in a
  background thread. Tolerances are ignored by these exact solvers.

1. **Core analysis and viewer.** Joint and mechanism model with R and P
   joints, position analysis for the four-bar and every slider variant,
   Grashof, and transmission angle. A minimal window where you pick a
   mechanism type, type its dimensions, and watch it animate with its
   coupler curve. Tests included. Includes a first version of the
   **library**: the Grashof classes and slider families as built-in
   entries, with animated previews, parameter sliders, and "Open in
   Analyze".
2. **Target editor.** The input side of the app, built before the solvers
   that consume it:
   - Canvas with pan and zoom, grid, units, and the full snapping system.
   - Pose, point, curve, and body tools, with ghost bodies.
   - Type-while-placing, inspector, and the keyframe table (including
     paste from spreadsheet).
   - Timeline strip with free, prescribed, and relative timing.
   - Pivot zones and fixed pivots.
   - Image and DXF underlays (see "Underlays").
   - Undo/redo through Qt's `QUndoStack`, built in from the start because
     it is painful to retrofit.
   - Project save/load (.json).
3. **Motion generation for 2 and 3 positions.** RR and slider dyad
   solvers, solutions table, defect checks, and live re-solve while you
   drag poses.
4. **Burmester synthesis for 4 and 5 positions.** Center-point and
   circle-point curves drawn on the canvas, pick pivots by clicking the
   curves. Ends of the curves at infinity and Ball points are offered as
   slider options.
5. **Path generation.** Optimizer running in a background thread with a
   progress bar and cancel button, diverse results. Also builds the
   **coupler-curve atlas** and "find similar" search (used to seed the
   optimizer), fills out the rest of the library catalog (straight-line
   linkages, common motions), and adds the "use as target", "seed the
   solver", and "save to library" actions.
6. **Function generation.** Freudenstein, Chebyshev spacing, error plot.
6b. **Motion-profile synthesis (to discuss).** Edit the kinematic plots
   directly and synthesize a mechanism that produces them.
   - **Editable profiles:** the output position, velocity and acceleration
     plots, and coupler-point speed, get draggable spline handles. You
     sketch "fast return, slow working stroke", "near-constant velocity
     over 90°", "dwell with low peak acceleration", and so on, or drag the
     current mechanism's curve into a new shape.
   - **What it becomes:** a target for the solver.
     - An output-position profile is function generation.
     - A velocity or acceleration profile is integrated to position, plus
       derivative terms in the objective.
     - A coupler-speed profile is path generation with timing.
   - **Exact option:** classical "higher-order" precision points. You
     specify position *and* velocity (and optionally acceleration) at a
     few input angles, and each one counts as extra precision conditions
     in the dyad / Freudenstein equations. So "hit this pose moving at this
     speed" can still be solved exactly for small cases.
   - **Consistency checks while editing:**
     - The velocity of a rocking output must integrate to zero over a
       cycle, since it returns to where it started.
     - Peak velocity and acceleration must be achievable at the chosen
       input speed.
     - Jerk and acceleration limits are shown as bands.
     - The editor keeps the three curves consistent. Dragging acceleration
       updates velocity and position, with position pinned at the
       precision points.
   - **Result:** the solver returns the closest achievable mechanism and
     overlays its actual curves on the requested ones, so the error is
     visible per region of the cycle.
7. **Polish for real use.** DXF, SVG, and CSV export, reports, and
   preferences.

8. **(Later) Physical design and CAD handoff.** Turn a chosen linkage into
   parts that can actually be made.
   - **Link generator:** real link shapes for **flat stock**, meaning
     laser, waterjet or plasma cut plate (for example from SendCutSend)
     rather than parts that need CNC machining.
     - Each link is a plate with rounded ends and pivot holes. The coupler
       is a plate outline enclosing its pivots and the coupler point.
     - Inputs: material thickness and hole sizes for the chosen pins,
       bolts or shoulder bolts, with bushings or bearings.
     - Checks: minimum edge distance around holes, and the stack-up order
       (which layer each link sits on, so the links clear each other).
     - Sliders become slotted plates or a guide rail.
   - **Flat-pattern export:** one DXF per part at 1:1 scale, with the
     material and thickness in the file name, ready to upload to
     SendCutSend or similar services. Also a bill of materials for pins,
     bushings, spacers and fasteners.
   - **Fusion 360 integration through its MCP server:** build the linkage
     in Fusion automatically.
     - Sketch and extrude each link to the stock thickness.
     - Stack the links in layers with spacers.
     - Create **as-built joints** (revolute for pins, slider for prismatic)
       and set their limits from the operating range.
     - The result can be animated and checked for interference in Fusion,
       then sent to Fusion's own sheet-metal and CAM workflows.
   - **Round trip:** the pivot locations and link lengths from kinsyn are
     the single source of truth, so re-running synthesis updates the
     Fusion model's parameters instead of rebuilding it.

Stretch goals: velocity and acceleration analysis, toggle positions and
mechanical advantage, tolerance sensitivity analysis, and possibly
multi-loop linkages (six-bars, five-bars) later on the same core.

## Environment notes

- System Python is 3.14 and SciPy is not installed. Use a project venv
  managed by `uv`. If PySide6 has no 3.14 wheel yet, pin Python 3.13 with
  `uv python pin 3.13`.
- Dependencies: `numpy scipy pyside6 pyqtgraph ezdxf` and, for development,
  `pytest`.
- `pyqtgraph` is used instead of matplotlib because it handles interactive
  dragging and 60 fps animation much better.

## Units

- **Internal storage:** always millimetres and radians, in the core, the
  solvers, and the saved files. The core never needs to know which units
  you're viewing in.
- **Display units:** mm, cm, m, or in. They can be switched at any time,
  from a status-bar dropdown or a preference.
  - Switching converts everything on screen live: fields, tables, grid
    spacing, and snapping increments.
  - The grid uses sensible steps for each unit: 1/5/10 mm, or
    1/16, 1/8, 1/4, and 1 in.
- **Defaults:** each project stores its own display unit, and there is a
  global default for new projects.
- **Angles:** shown in degrees everywhere, stored in radians.
- **Typing values with units:** any field accepts a unit suffix, whatever
  the current display unit, for example `2.5in`, `63.5mm`, or `1/4"`.
  The value is converted on entry.
- **Imports:** DXF uses the file's `$INSUNITS` (with an override option).
  Images get their scale from calibration.
- **Exports:** DXF and CSV are written in a unit you choose, and DXF sets
  `$INSUNITS` to match.
