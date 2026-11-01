"""``quantity.units``: a number with a unit, checked within a tolerance after unit conversion.

**Answer convention.** One number followed by an optional unit: ``"9.81 m/s^2"``, ``"981 cm/s**2"``,
``"1.2e3 N"``, ``"9.8 m/s²"`` (pint reads unicode superscripts), ``"9.8m/s^2"``. The number is
read by a strict regex (decimal point only -- ``"9,8"`` and ``"1,200"`` are format errors, never
silently read as 98 or 1200); only the unit text goes to pint's own unit parser (no ``eval``), so
arithmetic such as ``"2*3 m"`` is not accepted either.

**Judgement calls.**

- ``accepted_units`` given and the answer's unit is not one of them (compared as parsed pint
  units, so ``m/s^2`` == ``m/s²`` but ``kg*m/s^2`` != ``N``): a *format error* -- the answer is
  not in a form the question accepts, the same treatment as a wrong dimension.
- ``require_unit`` does not apply when ``unit`` is dimensionless: a bare number is then the
  natural answer.
- Significant figures follow the usual convention: leading zeros never count; trailing zeros of
  an integer without a decimal point do not count (``"1200"`` has 2, ``"1200."`` and ``"1.200e3"``
  have 4). Too few significant figures scores 0 with feedback saying so (not a format error).
- An expected ``value`` of 0 needs an ``absolute`` tolerance: a relative tolerance (including
  the default 1%) times 0 is 0, so only an exact 0 would pass and ``1e-17 N`` would be wrong.
  ``check_spec`` reports ``zero_value_needs_absolute`` instead of guessing one, because no
  unit-free default exists (0.001 is generous in ``N`` and tiny in ``mN``) -- the author knows
  the scale. ``grade`` itself is unchanged (exact 0 under a relative-only tolerance), so a spec
  stored before this check still grades as it always did rather than starting to raise.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pint
from pydantic import BaseModel, ConfigDict, Field

from graders.core import Grader, GradeResult, SpecError, SpecIssue, parse_spec
from graders.executors.base import Executor

#: Created once: building a registry parses pint's whole definitions file.
_UREG = pint.UnitRegistry()

MAX_ANSWER_CHARS = 200
DEFAULT_RELATIVE_TOLERANCE = 0.01

_NUMBER = re.compile(
    r"^\s*(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?P<unit>.*?)\s*$",
    re.DOTALL,
)


class Tolerance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative: float | None = Field(default=None, allow_inf_nan=False)
    #: In the spec's ``unit``.
    absolute: float | None = Field(default=None, allow_inf_nan=False)


class QuantitySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float = Field(allow_inf_nan=False)
    unit: str
    tolerance: Tolerance | None = None
    accepted_units: list[str] | None = None
    require_unit: bool = True
    sig_figs: int | None = None
    explanation: str | None = None


@dataclass(frozen=True)
class _Compiled:
    spec: QuantitySpec
    unit: pint.Unit
    accepted: tuple[pint.Unit, ...] | None
    relative: float | None
    absolute: float | None


def _parse_unit(text: str) -> pint.Unit:
    """Parse a unit string with pint; raises on anything pint cannot read."""
    if len(text) > MAX_ANSWER_CHARS:
        raise ValueError("unit text too long")
    return _UREG.parse_units(text)


def significant_figures(number: str) -> int:
    """Significant figures in a decimal number string (see module docstring for the rules)."""
    mantissa = re.split(r"[eE]", number.lstrip("+-"))[0]
    if "." in mantissa:
        digits = mantissa.replace(".", "").lstrip("0")
        if not digits:  # 0.0, 0.000: count the zeros after the point, at least one
            return max(1, len(mantissa.split(".")[1]))
        return len(digits)
    digits = mantissa.lstrip("0").rstrip("0")
    return max(1, len(digits))


def _spec_issues(spec: QuantitySpec) -> list[SpecIssue]:
    issues: list[SpecIssue] = []
    unit: pint.Unit | None = None
    try:
        unit = _parse_unit(spec.unit)
    except Exception:
        issues.append(SpecIssue("unknown_unit", f"The unit {spec.unit!r} is not recognised."))
    for accepted in spec.accepted_units or []:
        try:
            parsed = _parse_unit(accepted)
        except Exception:
            issues.append(
                SpecIssue("unknown_accepted_unit", f"Accepted unit {accepted!r} is not recognised.")
            )
            continue
        if unit is not None and parsed.dimensionality != unit.dimensionality:
            issues.append(
                SpecIssue(
                    "accepted_unit_dimension",
                    f"Accepted unit {accepted!r} does not measure the same quantity as "
                    f"{spec.unit!r}.",
                )
            )
    if spec.accepted_units is not None and not spec.accepted_units:
        issues.append(SpecIssue("no_accepted_units", "accepted_units is empty."))
    if spec.tolerance is not None:
        tolerances = [spec.tolerance.relative, spec.tolerance.absolute]
        if any(t is not None and t < 0 for t in tolerances):
            issues.append(SpecIssue("negative_tolerance", "Tolerances must not be negative."))
        if not any(t is not None and t > 0 for t in tolerances):
            issues.append(
                SpecIssue("no_tolerance", "Give a relative or absolute tolerance above 0.")
            )
    if spec.sig_figs is not None and spec.sig_figs < 1:
        issues.append(SpecIssue("bad_sig_figs", "sig_figs must be at least 1."))
    return issues


def _compile(raw: Mapping[str, Any]) -> _Compiled:
    spec = parse_spec(QuantitySpec, raw)
    assert isinstance(spec, QuantitySpec)
    issues = _spec_issues(spec)
    if issues:
        raise SpecError("; ".join(issue.message for issue in issues))
    if spec.tolerance is None:
        relative, absolute = DEFAULT_RELATIVE_TOLERANCE, None
    else:
        relative, absolute = spec.tolerance.relative, spec.tolerance.absolute
    accepted = (
        tuple(_parse_unit(u) for u in spec.accepted_units)
        if spec.accepted_units is not None
        else None
    )
    return _Compiled(spec, _parse_unit(spec.unit), accepted, relative, absolute)


def _within(diff: float, bound: float | None) -> bool:
    # isclose so that an answer exactly on the boundary passes despite float error.
    return bound is not None and (diff <= bound or math.isclose(diff, bound, rel_tol=1e-9))


def _join(*parts: str | None) -> str | None:
    text = " ".join(part for part in parts if part)
    return text or None


class QuantityGrader:
    capability = "quantity.units"
    version = "1"
    spec_model = QuantitySpec

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        try:
            parsed = parse_spec(QuantitySpec, spec)
        except SpecError as error:
            return [SpecIssue("invalid_spec", str(error))]
        assert isinstance(parsed, QuantitySpec)
        issues = _spec_issues(parsed)
        absolute = parsed.tolerance.absolute if parsed.tolerance is not None else None
        if parsed.value == 0 and not (absolute is not None and absolute > 0):
            issues.append(
                SpecIssue(
                    "zero_value_needs_absolute",
                    "The expected value is 0, so a relative tolerance accepts only an exact 0; "
                    "give an absolute tolerance (in the spec's unit).",
                )
            )
        if not issues:
            # The reference answer itself must score full marks (sig figs aside: repr() of the
            # value need not carry them; accepted_units may deliberately exclude the spec's unit).
            reference = {**dict(spec), "sig_figs": None, "accepted_units": None}
            result = self.grade(reference, f"{parsed.value!r} {parsed.unit}")
            if result.score != 1.0:
                issues.append(
                    SpecIssue(
                        "reference_fails",
                        f"The reference value does not grade as correct: "
                        f"{result.format_error or result.feedback}",
                    )
                )
        return issues

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        compiled = _compile(spec)
        explanation = compiled.spec.explanation

        def wrong(format_error: str) -> GradeResult:
            return GradeResult(score=0.0, feedback=explanation, format_error=format_error)

        if len(answer) > MAX_ANSWER_CHARS:
            return wrong(f"The answer is longer than {MAX_ANSWER_CHARS} characters.")
        if "," in answer:
            return wrong("Use a decimal point, not a comma (e.g. 9.81, not 9,81 or 1,200).")
        match = _NUMBER.match(answer)
        if match is None:
            return wrong("Start the answer with a number, e.g. '9.81 m/s^2'.")
        number_text, unit_text = match["number"], match["unit"]
        number = float(number_text)
        if not math.isfinite(number):
            return wrong("The number is out of range.")

        target = compiled.unit
        if unit_text:
            try:
                answer_unit = _parse_unit(unit_text)
            except Exception:
                return wrong(f"The unit {unit_text!r} is not recognised.")
        elif compiled.spec.require_unit and not target.dimensionless:
            return wrong(f"Give a unit (the answer is a quantity in {compiled.spec.unit}).")
        else:
            answer_unit = target

        if answer_unit.dimensionality != target.dimensionality:
            return wrong(
                f"The unit {unit_text or 'dimensionless'!r} doesn't match: the answer should be "
                f"a quantity in {compiled.spec.unit or 'dimensionless'}."
            )
        if (
            compiled.accepted is not None
            and unit_text
            and not any(answer_unit == accepted for accepted in compiled.accepted)
        ):
            allowed = ", ".join(compiled.spec.accepted_units or [])
            return wrong(f"Give the answer in one of these units: {allowed}.")

        try:
            converted = float(_UREG.Quantity(number, answer_unit).to(target).magnitude)
        except Exception:
            return wrong(f"The unit {unit_text!r} cannot be converted to {compiled.spec.unit}.")

        if compiled.spec.sig_figs is not None:
            given = significant_figures(number_text)
            if given < compiled.spec.sig_figs:
                note = (
                    f"Give at least {compiled.spec.sig_figs} significant figures "
                    f"(the answer has {given})."
                )
                return GradeResult(score=0.0, feedback=_join(explanation, note))

        diff = abs(converted - compiled.spec.value)
        relative_bound = (
            None if compiled.relative is None else compiled.relative * abs(compiled.spec.value)
        )
        correct = _within(diff, compiled.absolute) or _within(diff, relative_bound)
        return GradeResult(score=1.0 if correct else 0.0, feedback=explanation)


def build(executor_factory: Callable[[], Executor]) -> list[Grader]:
    del executor_factory  # no code runs
    return [QuantityGrader()]
