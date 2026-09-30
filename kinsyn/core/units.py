"""Unit handling. Internally everything is millimetres and radians; units only
exist at the UI boundary (display formatting and parsing typed input)."""

import ast
import math
import operator
import re

LENGTH_UNITS = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}

_LENGTH_SUFFIX = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, '"': 25.4,
                  "ft": 304.8, "'": 304.8}
_ANGLE_SUFFIX = {"deg": math.pi / 180, "°": math.pi / 180, "rad": 1.0}

_NUM = r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_LEN_TAG = r"mm|cm|ft|in|m|\"|'"
_ANG_TAG = r"deg|°|rad"

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_NAMES = {"pi": math.pi}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and len(node.args) == 1):
        return _FUNCS[node.func.id](_eval(node.args[0]))
    raise ValueError("unsupported expression")


def _expr(text):
    try:
        return _eval(ast.parse(text, mode="eval"))
    except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(str(exc)) from exc


def _parse(text, tags, suffixes, default_factor):
    s = text.strip()
    if not s:
        raise ValueError("empty")
    # Mixed fractions: 1 1/4 -> (1+1/4)
    s = re.sub(r"(\d+)\s+(\d+)\s*/\s*(\d+)", r"(\1+\2/\3)", s)
    tag_re = re.compile(rf"({_NUM})\s*({tags})(?![A-Za-z])")
    # A single trailing unit applies to the whole expression: "1/4 in", "(2+3)mm".
    trailing = re.fullmatch(rf"(.*?)\s*({tags})", s)
    if trailing and not tag_re.search(trailing.group(1)):
        return _expr(trailing.group(1)) * suffixes[trailing.group(2)]
    if tag_re.search(s):
        # Per-number units; untagged numbers are plain scalars.
        return _expr(tag_re.sub(lambda m: f"({m.group(1)}*{suffixes[m.group(2)]!r})", s))
    return _expr(s) * default_factor


def parse_length(text, unit="mm"):
    """Parse a length like '2.5in', '1 1/4"', '2*25.4', '63.5 mm' into mm.
    Untagged values are in `unit`."""
    return _parse(text, _LEN_TAG, _LENGTH_SUFFIX, LENGTH_UNITS[unit])


def parse_angle(text):
    """Parse an angle into radians. Untagged values are degrees."""
    return _parse(text, _ANG_TAG, _ANGLE_SUFFIX, math.pi / 180)


def _fmt(v, digits):
    s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def format_length(mm, unit="mm", digits=None):
    if digits is None:
        digits = {"mm": 3, "cm": 4, "m": 6, "in": 4}[unit]
    return _fmt(mm / LENGTH_UNITS[unit], digits)


def format_angle(rad, digits=3):
    return _fmt(math.degrees(rad), digits)
