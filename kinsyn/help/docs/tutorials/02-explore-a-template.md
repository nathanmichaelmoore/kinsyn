# Explore a template

The fastest way to build intuition is to take a working mechanism and
change it.

## 1. Load one

In the **Library** tab, click **Crank-rocker** (under *Grashof classes*).
It starts animating. The **blue curve** is the path of the
[coupler point](../concepts/coupler-point.md). The dashed curve is the
same linkage put together the [other way](../concepts/assemblies-and-circuits.md).

## 2. Read the summary

The **Mechanism** tab lists what kind of linkage this is and how well it
works:

- **Class**: *Crank-rocker*. The input turns all the way round and the
  output swings back and forth. See [Grashof](../concepts/grashof.md).
- **Transmission angle**, worst value in green or red. See
  [Transmission angle](../concepts/transmission-angle.md).
- **Time ratio**: how much longer one swing takes than the other. See
  [Quick return](../concepts/time-ratio.md).

Terms in the summary are links: click one to jump to its explanation.

## 3. Change it

Drag the **Coupler b** slider. Watch:

- the coupler curve change shape;
- the transmission angle go red if it drops below the limit;
- the class change to *Triple-rocker* if the input can no longer turn all
  the way round.

You can also type exact values, like `85`, `3.5in` or `2*25.4`. See
[Entering values](../reference/entering-values.md).

## 4. Put it back

The header shows **(modified)**. Press **Reset** (Ctrl+R) to go back to the
template.

## 5. Look at the motion

Pause (**Space**) and drag the orange cursor on any plot to step through
the cycle. Switch a plot to **Output acceleration** to see how unevenly
the output moves even though the input turns steadily. See
[Velocity and acceleration](../concepts/velocity-acceleration.md).

**Next:** [Define a motion](03-define-a-motion.md)
