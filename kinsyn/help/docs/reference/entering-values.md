# Entering values and units

## Units

Pick **mm, cm, m or in** from the **Units** menu in the status bar. Every
field, table, axis and grid step converts instantly. Internally kinsyn
always stores millimetres, so switching units never loses precision.

## What you can type in a length field

| You type | Means |
|---|---|
| `12.5` | 12.5 in the current display unit |
| `2.5in`, `2.5"` | 2.5 inches, whatever the display unit |
| `63.5 mm`, `3 cm`, `0.1 m`, `1ft` | explicit units |
| `1 1/4"` | 1¼ inches |
| `2*25.4`, `(10+5)/2` | arithmetic |
| `1in + 3mm` | mixed units (the result is converted) |

A field with a red outline couldn't be read. Hover over it for examples.

## Angles

Angles are in **degrees** unless you say otherwise: `30`, `30°`,
`0.5 rad`, `pi/4 rad`.

## Coordinates on the canvas

Start typing while the canvas has focus (or click the box in the status
bar):

| You type | Means |
|---|---|
| `120, 45` | the point (120, 45) |
| `120, 45, 30` | the point (120, 45) with a 30° angle (poses) |
| `@20, -10` | 20 right and 10 down from the last point |
| `@0, 0, 15` | same place, rotated a further 15° |

Press **Enter** to apply.

## Pasting from a spreadsheet

In the **Target** tab, **Paste** reads rows of `x, y` or `x, y, angle`,
separated by tabs, commas or semicolons. A header row is skipped
automatically. Values are read in the current display unit.
