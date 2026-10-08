"""Calculator and unit/currency conversion. Exact arithmetic instead of letting the model guess."""
import ast
import json
import math
import operator
import urllib.parse
import urllib.request

KEYWORDS = ["calculate", "what's ", "whats ", "how much is", "percent", "%", "convert", " to km", " to miles",
            "divided", "times", "plus", "minus", "square root", "tip", "usd", "gbp", "inr", "eur", "dollar",
            "pound", "rupee", "celsius", "fahrenheit", "kg", "miles", "litre", "km"]

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log, "log10": math.log10, "ceil": math.ceil, "floor": math.floor}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def calculate(expression: str) -> str:
    """Evaluate arithmetic like '18% of 2450' written as '2450 * 0.18', or 'sqrt(144) + 3**2'."""
    expr = expression.replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "").strip()
    if len(expr) > 200:
        return "ERROR: Expression too long."
    try:
        result = _eval(ast.parse(expr, mode="eval").body)
    except ZeroDivisionError:
        return "ERROR: Division by zero."
    except (ValueError, SyntaxError, TypeError, OverflowError) as e:
        return f"ERROR: Cannot evaluate that ({e}). Use numbers and + - * / ** % sqrt()."
    return f"{expression.strip()} = {round(result, 10):,}" if isinstance(result, float) else f"{expression.strip()} = {result:,}"


# unit -> (dimension, factor to the dimension's base unit)
_UNITS = {
    "mm": ("len", 0.001), "cm": ("len", 0.01), "m": ("len", 1), "km": ("len", 1000), "inch": ("len", 0.0254),
    "in": ("len", 0.0254), "ft": ("len", 0.3048), "foot": ("len", 0.3048), "feet": ("len", 0.3048),
    "yard": ("len", 0.9144), "yd": ("len", 0.9144), "mile": ("len", 1609.344), "miles": ("len", 1609.344),
    "mi": ("len", 1609.344),
    "g": ("mass", 0.001), "kg": ("mass", 1), "lb": ("mass", 0.45359237), "lbs": ("mass", 0.45359237),
    "pound": ("mass", 0.45359237), "oz": ("mass", 0.028349523125), "stone": ("mass", 6.35029318), "tonne": ("mass", 1000),
    "ml": ("vol", 0.001), "l": ("vol", 1), "litre": ("vol", 1), "liter": ("vol", 1), "gallon": ("vol", 4.54609),
    "usgallon": ("vol", 3.785411784), "pint": ("vol", 0.56826125), "cup": ("vol", 0.2365882365),
    "mph": ("speed", 0.44704), "kph": ("speed", 0.2777777778), "kmh": ("speed", 0.2777777778), "km/h": ("speed", 0.2777777778),
    "m/s": ("speed", 1), "knot": ("speed", 0.514444),
    "sec": ("time", 1), "min": ("time", 60), "hour": ("time", 3600), "day": ("time", 86400), "week": ("time", 604800),
    "b": ("data", 1), "kb": ("data", 1e3), "mb": ("data", 1e6), "gb": ("data", 1e9), "tb": ("data", 1e12),
}
_TEMPS = {"c": "c", "celsius": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k"}
_CURRENCY = {"usd", "gbp", "eur", "inr", "aud", "cad", "jpy", "chf", "cny", "aed", "sgd", "nzd", "sek", "zar"}


def _norm(u: str) -> str:
    u = u.strip().lower().rstrip(".")
    for suffix in ("s",):
        if u.endswith(suffix) and u[:-1] in _UNITS | _TEMPS:
            u = u[:-1]
    return {"kilometre": "km", "kilometer": "km", "metre": "m", "meter": "m", "kilogram": "kg", "gram": "g",
            "centimetre": "cm", "centimeter": "cm", "millilitre": "ml", "pounds": "lb", "kilometres": "km",
            "kilometers": "km", "hours": "hour", "minutes": "min", "seconds": "sec", "days": "day"}.get(u, u)


def convert(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between units (length, mass, volume, speed, time, data, temperature) or currencies (e.g. GBP to INR)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "ERROR: The value must be a number."
    a, b = _norm(from_unit), _norm(to_unit)
    if a in _CURRENCY and b in _CURRENCY:
        try:
            url = "https://api.frankfurter.dev/v1/latest?" + urllib.parse.urlencode({"amount": value, "base": a.upper(), "symbols": b.upper()})
            req = urllib.request.Request(url, headers={"User-Agent": "jarvis-assistant/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
            return f"{value:,} {a.upper()} = {data['rates'][b.upper()]:,} {b.upper()} (rate on {data['date']}, ECB)"
        except Exception:
            return "ERROR: Could not fetch the exchange rate right now."
    if a in _TEMPS and b in _TEMPS:
        x, y = _TEMPS[a], _TEMPS[b]
        celsius = value if x == "c" else (value - 32) * 5 / 9 if x == "f" else value - 273.15
        out = celsius if y == "c" else celsius * 9 / 5 + 32 if y == "f" else celsius + 273.15
        return f"{value:g} {a} = {out:.2f} {b}"
    if a in _UNITS and b in _UNITS:
        if _UNITS[a][0] != _UNITS[b][0]:
            return f"ERROR: Cannot convert {_UNITS[a][0]} to {_UNITS[b][0]}."
        return f"{value:g} {from_unit} = {value * _UNITS[a][1] / _UNITS[b][1]:,.6g} {to_unit}"
    return f"ERROR: I don't know how to convert '{from_unit}' to '{to_unit}'."


def _t(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


TOOLS = [
    _t("calculate", "Exact calculator. ALWAYS use for any arithmetic or percentage; never do maths yourself. "
       "Write percentages as multiplication, e.g. 18% of 2450 -> 2450*0.18.",
       {"expression": {"type": "string"}}, ["expression"]),
    _t("convert", "Convert units (km, miles, kg, lb, litres, mph, celsius...) or currencies (GBP, INR, USD, EUR...).",
       {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}},
       ["value", "from_unit", "to_unit"]),
]
FUNCTIONS = {"calculate": calculate, "convert": convert}
