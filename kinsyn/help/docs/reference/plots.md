# Plots

The four plots under the canvas show how the mechanism behaves over one
cycle. The horizontal axis is **circuit position (%)**: 0 to 100% of one
full cycle of motion.

Each plot has a **dropdown** to choose what it shows:

| Quantity | What it tells you |
|---|---|
| Transmission angle | How well force passes from the coupler to the output. Red bands are the zones to avoid. [More](../concepts/transmission-angle.md) |
| Output position | The output angle (or slider position) through the cycle. |
| Output velocity | How fast the output moves, at the set input speed. [More](../concepts/velocity-acceleration.md) |
| Output acceleration | How quickly the output speeds up and slows down. It drives inertia forces. |
| Coupler point speed | How fast the coupler point moves along its curve. |
| Coupler point acceleration | How hard the coupler point is thrown around. It peaks at sharp turns. |
| Mechanical advantage | Output force per input force (log scale). It spikes at toggles. [More](../concepts/mechanical-advantage.md) |

**Scrubbing:** drag the orange cursor on any plot (or the scrub bar) to
move the mechanism to that point in the cycle. The readout next to the
scrub bar shows the exact values there.

Your plot choices are remembered between sessions.
