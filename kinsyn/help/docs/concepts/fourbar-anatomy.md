# Anatomy of a four-bar

![Parts of a four-bar linkage](../img/fourbar-anatomy.svg)

A four-bar linkage is four rigid links joined by four pins in a closed loop.
It is the simplest linkage that does something interesting, and it's
everywhere: car suspensions, windshield wipers, folding chairs, excavator
arms, cabinet hinges.

| Link | What it does |
|---|---|
| **Ground** | The fixed frame. Its two pivots, **A0** and **B0**, never move. It counts as a link even though it's just "the machine". |
| **Input link (a)** | The link you drive, with a motor, handle or cylinder. It's called a **crank** if it can turn all the way round. |
| **Coupler (b)** | The floating link joining the input and output links. It both moves and rotates, so points on it follow rich curves. |
| **Output link (c)** | The second grounded link. It's called a **rocker** if it swings back and forth. |

## Why "the coupler" matters

The input and output links can only rotate about their fixed pivots. The
coupler is the only link that moves *freely* through the plane. That's why:

- **motion generation** designs the coupler to carry a part through
  given poses;
- **path generation** designs a **[coupler point](coupler-point.md)** to
  trace a given curve.

## In kinsyn

The Mechanism tab lists the pivots (A0, B0) and lengths (a, b, c). The
ground length is the distance between the pivots. Hover over any label
for a reminder.

Related: [Grashof condition](grashof.md) (which links can turn all the
way round) · [Slider mechanisms](slider-mechanisms.md) (when one pin
becomes a slider)
