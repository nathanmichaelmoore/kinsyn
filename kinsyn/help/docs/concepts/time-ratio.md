# Quick return and time ratio

When a crank turns steadily and the output swings back and forth, the two
swings don't have to take the same time.

**Time ratio** = time of the slower stroke ÷ time of the faster stroke
(always ≥ 1).

- **1.0**: both strokes take equal time (for example, an in-line
  slider-crank).
- **Above 1**: a **quick return**. One stroke is slow (use it for the
  working stroke, like cutting or pushing), and the other snaps back
  quickly, so less time is wasted.

Shaping machines use this directly: the *Whitworth* and *crank-shaper*
templates in the library are classic quick-return drives. An **offset**
slider-crank gives a mild quick return too.

## In kinsyn

When the input turns fully and the output swings, the summary shows
**Time ratio**. Compare the *Slider-crank, in-line* (1.0) and *offset*
(about 1.12) templates to see the effect of the offset.
