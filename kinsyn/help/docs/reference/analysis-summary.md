# Reading the analysis summary

The **Mechanism** tab summarises the current linkage. Each line, in order:

| Line | Meaning |
|---|---|
| **Class** | The linkage type, e.g. *Crank-rocker*. See [Grashof](../concepts/grashof.md). |
| **Input** | *rotates fully*, or *rocks* between two limits (its swing range). |
| **Output travel** | How far the output swings or slides, and between which values. |
| **Transmission angle** | Its range over the motion and the worst value, green if acceptable and red if below the limit. See [Transmission angle](../concepts/transmission-angle.md). |
| **Time ratio** | Slow stroke ÷ fast stroke. See [Quick return](../concepts/time-ratio.md). |
| **Toggle positions** | Input angles where the input and coupler line up. See [Toggle](../concepts/toggle-over-center.md). |
| **Over-center** | How far past the toggle the operating range ends (clamps and latches). |

Below the table, **red lines are warnings** (for example, the transmission
angle is too small) and **plain lines are notes** (for example, the
Grashof inequality, or whether the slider is in-line).

## Motion box

- **Circuit**: which continuous cycle to show, when there is more than
  one. See [Assemblies and circuits](../concepts/assemblies-and-circuits.md).
- **Limit input to an operating range**: analyse only the part of the
  motion you use, from one angle (or length) to another.
- **Input speed**: used for the velocity and acceleration plots.
