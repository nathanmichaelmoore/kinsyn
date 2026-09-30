# Kinematic synthesis

**Analysis** asks: *given this linkage, how does it move?*
**Synthesis** asks the reverse: *given the motion I need, what linkage
produces it?* That's what kinsyn is built for.

## Three kinds of problem

| Type | You specify | Example |
|---|---|---|
| **Motion generation** | **poses** (position + angle) the moving part must reach | a hood that must lift and tilt to clear the windshield |
| **Path generation** | **points or a curve** a point must travel along | a feeder claw that must trace a D-shaped path |
| **Function generation** | how the **output angle** must depend on the input angle | a mechanical calculator, a throttle linkage |

## Precision points vs. approximation

- A keyframe with **zero tolerance** is a **precision point**: the
  mechanism must pass through it *exactly*.
- Exact methods can handle only a few precision points: up to **5 poses**
  for motion generation with a four-bar. With more, or with tolerances,
  kinsyn uses an **optimizer**, which finds the linkage that comes closest.

The hint at the top of the Target tab tells you which applies:

| Your target | Method |
|---|---|
| 2 poses | many solutions; you choose the free parameters |
| 3 poses | dyad solve (a small linear system) |
| 4 poses | **Burmester curves**: every point on the curve is a valid pivot |
| 5 poses | **Burmester points**: a handful of exact solutions |
| more, or with tolerance | optimization |

## Timing

By default the solver decides *when* (at what input angle) each keyframe
is reached: **free timing**. Fixing the timing makes the problem much
harder, so use it only where it truly matters.

## After solving

Every candidate is then checked:

- [Grashof class](grashof.md) (if full rotation is required);
- [transmission angle](transmission-angle.md);
- all poses on one [circuit](assemblies-and-circuits.md), in order;
- pivots inside your allowed zones.

Candidates that fail are listed with the reason, so you can see why they
were rejected.

> The solvers are being built next (milestones 3 to 6). Setting up targets
> is already fully supported.
