"""Help topics: table of contents and one-line definitions used for
tooltips and "?" links across the app."""

from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"

TOC = [
    ("Getting started", [
        ("Welcome", "index.md"),
        ("Tour of the window", "tutorials/01-tour.md"),
        ("Explore a template", "tutorials/02-explore-a-template.md"),
        ("Define a motion: poses, body, snapping", "tutorials/03-define-a-motion.md"),
        ("Find a linkage for 2 or 3 poses", "tutorials/04-motion-generation.md"),
    ]),
    ("Concepts", [
        ("Anatomy of a four-bar", "concepts/fourbar-anatomy.md"),
        ("Coupler point and coupler curve", "concepts/coupler-point.md"),
        ("Grashof condition", "concepts/grashof.md"),
        ("Transmission angle", "concepts/transmission-angle.md"),
        ("Assemblies and circuits", "concepts/assemblies-and-circuits.md"),
        ("Toggle and over-center", "concepts/toggle-over-center.md"),
        ("Mechanical advantage", "concepts/mechanical-advantage.md"),
        ("Velocity and acceleration", "concepts/velocity-acceleration.md"),
        ("Quick return and time ratio", "concepts/time-ratio.md"),
        ("Slider mechanisms", "concepts/slider-mechanisms.md"),
        ("Kinematic synthesis", "concepts/synthesis.md"),
    ]),
    ("Reference", [
        ("Tools and shortcuts", "reference/tools-and-shortcuts.md"),
        ("Entering values and units", "reference/entering-values.md"),
        ("Analysis summary", "reference/analysis-summary.md"),
        ("Plots", "reference/plots.md"),
    ]),
]

# key -> (title, one-line definition, doc path)
TERMS = {
    "ground": ("Ground", "The fixed frame the mechanism is mounted to. Ground pivots (A0, B0) never move.",
               "concepts/fourbar-anatomy.md"),
    "input-link": ("Input link (crank)", "The link you drive, with a motor, handle or actuator. It is called a "
                   "crank if it can turn all the way round.", "concepts/fourbar-anatomy.md"),
    "coupler": ("Coupler", "The floating link that connects the input and output links. It moves in the most "
                "interesting way, because it both translates and rotates.", "concepts/fourbar-anatomy.md"),
    "output-link": ("Output link", "The second grounded link. It is called a rocker if it swings back and forth.",
                    "concepts/fourbar-anatomy.md"),
    "coupler-point": ("Coupler point", "A point fixed to the coupler. Its path, the coupler curve, is what path "
                      "generation shapes.", "concepts/coupler-point.md"),
    "assembly": ("Assembly", "For the same link lengths and input angle a linkage can usually be put together "
                 "two ways (+1 / −1).", "concepts/assemblies-and-circuits.md"),
    "circuit": ("Circuit", "One continuous cycle the mechanism can move through without being taken apart.",
                "concepts/assemblies-and-circuits.md"),
    "grashof": ("Grashof condition", "s + l ≤ p + q: when it holds, at least one link can turn all the way round.",
                "concepts/grashof.md"),
    "transmission-angle": ("Transmission angle", "Angle between the coupler and the output link. Near 90° pushes "
                           "well; below about 40° the linkage tends to bind.", "concepts/transmission-angle.md"),
    "toggle": ("Toggle", "Position where the input link and coupler line up: the output stops, and force "
               "multiplication is at its maximum.", "concepts/toggle-over-center.md"),
    "over-center": ("Over-center", "Going slightly past the toggle onto a stop, so a load cannot push the "
                    "mechanism back open.", "concepts/toggle-over-center.md"),
    "mechanical-advantage": ("Mechanical advantage", "Output force (or torque) per unit of input force, "
                             "ignoring friction. It is very large near a toggle.",
                             "concepts/mechanical-advantage.md"),
    "velocity": ("Velocity", "How fast something moves at a constant input speed. Most linkages turn a steady "
                 "input into an uneven output.", "concepts/velocity-acceleration.md"),
    "acceleration": ("Acceleration", "How quickly the velocity changes. It sets the inertia forces, "
                     "vibration and wear.", "concepts/velocity-acceleration.md"),
    "coupler-acceleration": ("Coupler point acceleration", "How hard the coupler point is being pushed "
                             "around its path. It is high at tight turns and cusps of the coupler curve.",
                             "concepts/velocity-acceleration.md"),
    "time-ratio": ("Time ratio", "Duration of the slower stroke divided by the faster one. A value above 1 "
                   "means a quick return.", "concepts/time-ratio.md"),
    "operating-range": ("Operating range", "The part of the input's travel you actually use, for example from "
                        "a clamp's open position to its stop.", "concepts/toggle-over-center.md"),
    "slider-offset": ("Slider offset", "Perpendicular distance from the crank pivot to the slider's line of "
                      "travel. 0 means in-line.", "concepts/slider-mechanisms.md"),
    "synthesis": ("Kinematic synthesis", "Working backwards from a desired motion to the dimensions of a "
                  "mechanism that produces it.", "concepts/synthesis.md"),
    "pose": ("Pose", "A position and an angle that the moving part must reach (motion generation).",
             "tutorials/03-define-a-motion.md"),
    "precision-point": ("Precision point", "A keyframe that must be hit exactly (tolerance 0). Exact solvers "
                        "can handle up to 5 poses.", "concepts/synthesis.md"),
    "timing": ("Timing", "Whether a keyframe must be reached at a particular input angle (prescribed) or "
               "whenever the mechanism gets there (free).", "concepts/synthesis.md"),
    "dyad": ("Dyad", "Two links' worth of a mechanism: one ground pivot, one link, and one joint on the moving "
             "part. Two dyads together make a four-bar or slider-crank.", "concepts/synthesis.md"),
    "branch-defect": ("Branch defect", "The design reaches some poses in one assembly and others in the other "
                      "assembly. The real linkage can't switch without being taken apart.", "concepts/synthesis.md"),
    "order-defect": ("Order defect", "The design passes through all the poses, but not in the order you set.",
                     "concepts/synthesis.md"),
    "circuit-defect": ("Circuit defect", "The poses lie on separate pieces of the motion, so the input can't "
                       "move from one to the next without the linkage coming apart.", "concepts/synthesis.md"),
    "fixed-pivot": ("Fixed pivot", "A ground pivot you place yourself (Pivot tool, G). Every design the search "
                    "finds then uses it.", "tutorials/04-motion-generation.md"),
    "snapping": ("Snapping", "Placement that locks to the grid, existing points, alignment lines or 15° "
                 "angles. S toggles it; hold Alt to place freely.", "tutorials/03-define-a-motion.md"),
}

# Plot quantity key -> term key
PLOT_TERMS = {"mu": "transmission-angle", "out": "output-link", "out_vel": "velocity", "out_acc": "acceleration",
              "p_speed": "velocity", "p_acc": "coupler-acceleration", "ma": "mechanical-advantage"}

# Mechanism parameter name -> term key (for editor tooltips)
PARAM_TERMS = {"a": "input-link", "b": "coupler", "c": "output-link", "P": "coupler-point", "branch": "assembly",
               "e": "slider-offset", "A0": "ground", "B0": "ground"}


def tooltip(term):
    title, short, _ = TERMS[term]
    return f"<b>{title}</b><br>{short}<br><i>F1 / Help for more</i>"


def all_doc_paths():
    return [path for _, items in TOC for _, path in items]
