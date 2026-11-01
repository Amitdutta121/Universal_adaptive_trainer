"""A tiny, safe arithmetic evaluator for an answer key's stated calculation.

Parses with :mod:`ast` and evaluates only numbers, + - * / ** (``^`` is read as power),
unary minus, parentheses, ``pi``/``e`` and a few functions -- no names, attributes, calls to
anything else, comprehensions or subscripts, so text written by a model is never executed.
Trigonometric functions take degrees, as a physics prompt states angles.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable

MAX_LENGTH = 300
MAX_POWER = 1000

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_FUNCTIONS: dict[str, Callable[[float], float]] = {
    "sqrt": math.sqrt,
    "sin": lambda x: math.sin(math.radians(x)),
    "cos": lambda x: math.cos(math.radians(x)),
    "tan": lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "exp": math.exp,
    "ln": math.log,
    "log10": math.log10,
    "abs": abs,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}


def evaluate_arithmetic(text: str) -> float:
    """The value of ``text``. ``ValueError`` for anything that is not plain arithmetic."""
    if len(text) > MAX_LENGTH:
        raise ValueError("the calculation is too long")
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
    except SyntaxError as error:
        raise ValueError("the calculation is not a valid expression") from error
    try:
        result = _eval(tree.body)
    except (ArithmeticError, TypeError) as error:
        raise ValueError(f"the calculation cannot be evaluated ({error})") from error
    if not math.isfinite(result):
        raise ValueError("the calculation is not a finite number")
    return result


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        operand = _eval(node.operand)
        return -operand if isinstance(node.op, ast.USub) else operand
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_POWER:
            raise ValueError("an exponent in the calculation is too large")
        return float(_BINARY[type(node.op)](left, right))
    if isinstance(node, ast.Name) and node.id in _CONSTANTS:
        return _CONSTANTS[node.id]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCTIONS
        and len(node.args) == 1
        and not node.keywords
    ):
        return float(_FUNCTIONS[node.func.id](_eval(node.args[0])))
    raise ValueError(f"'{ast.unparse(node)}' is not plain arithmetic")


__all__ = ["evaluate_arithmetic"]
