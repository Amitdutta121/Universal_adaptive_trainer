"""quantity.units (C3): value + unit, tolerance, conversion via pint, sig figs."""

from __future__ import annotations

from typing import Any

import pytest

import graders
from graders import SpecError
from graders.quantity import QuantityGrader, build, significant_figures

G = QuantityGrader()
ACCEL: dict[str, Any] = {"value": 9.81, "unit": "m/s^2"}


def grade(answer: str, **spec: Any):
    return G.grade({**ACCEL, **spec}, answer)


def codes(spec: dict[str, Any]) -> set[str]:
    return {issue.code for issue in G.check_spec(spec)}


# --- correct / wrong -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "answer",
    ["9.81 m/s^2", "9.81 m/s**2", "9.81m/s^2", "  9.81 m / s^2 ", "981 cm/s^2", "9.81 m s^-2"],
)
def test_correct_answers_and_conversion(answer: str) -> None:
    result = grade(answer)
    assert result.score == 1.0, result
    assert result.format_error is None


def test_unicode_superscript_is_read_by_pint() -> None:
    assert grade("9.81 m/s²").score == 1.0


def test_scientific_notation() -> None:
    assert G.grade({"value": 1200, "unit": "N"}, "1.2e3 N").score == 1.0
    assert G.grade({"value": 1200, "unit": "N"}, "1.2 kN").score == 1.0


def test_relative_tolerance() -> None:
    tolerance = {"relative": 0.02}
    assert grade("9.7 m/s^2", tolerance=tolerance).score == 1.0
    wrong = grade("9.0 m/s^2", tolerance=tolerance)
    assert wrong.score == 0.0 and wrong.format_error is None


def test_default_tolerance_is_one_percent() -> None:
    assert grade("9.9 m/s^2").score == 1.0  # 0.92 %
    assert grade("9.7 m/s^2").score == 0.0  # 1.1 %


def test_absolute_tolerance_edges() -> None:
    tolerance = {"absolute": 0.1}
    assert grade("9.91 m/s^2", tolerance=tolerance).score == 1.0  # exactly on the boundary
    assert grade("9.71 m/s^2", tolerance=tolerance).score == 1.0
    assert grade("9.92 m/s^2", tolerance=tolerance).score == 0.0
    # absolute is in the spec's unit, applied after conversion
    assert grade("991 cm/s^2", tolerance=tolerance).score == 1.0


def test_either_tolerance_is_enough() -> None:
    tolerance = {"relative": 0.001, "absolute": 0.5}
    assert grade("10.2 m/s^2", tolerance=tolerance).score == 1.0
    tolerance = {"relative": 0.1, "absolute": 0.001}
    assert grade("10.2 m/s^2", tolerance=tolerance).score == 1.0


def test_relative_tolerance_on_zero_value_needs_exact() -> None:
    assert G.grade({"value": 0, "unit": "N"}, "0 N").score == 1.0
    assert G.grade({"value": 0, "unit": "N"}, "0.001 N").score == 0.0


# --- format errors ---------------------------------------------------------------------------


def test_bare_number_requires_unit_by_default() -> None:
    result = grade("9.81")
    assert result.score == 0.0 and "Give a unit" in (result.format_error or "")


def test_bare_number_read_in_spec_unit_when_unit_not_required() -> None:
    assert grade("9.81", require_unit=False).score == 1.0
    assert grade("5", require_unit=False).score == 0.0


def test_wrong_dimension_is_format_error() -> None:
    result = grade("9.8 m")
    assert result.score == 0.0
    assert "doesn't match" in (result.format_error or "")


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "about ten",
        "m/s^2",
        "9.8 furlongs-ish",
        "9.8 m/s^2)",
        "__import__('os').system('echo hi')",
        "9.8 __import__",
        "2*3 m/s^2",
        "nan m/s^2",
        "inf m/s^2",
        "9" * 300,
    ],
)
def test_unreadable_answers_are_format_errors(answer: str) -> None:
    result = grade(answer)
    assert result.score == 0.0
    assert result.format_error


@pytest.mark.parametrize("answer", ["9,81 m/s^2", "9,8 m/s^2", "1,200 N"])
def test_comma_is_a_format_error_not_a_decimal(answer: str) -> None:
    result = grade(answer)
    assert result.score == 0.0 and "comma" in (result.format_error or "")


def test_accepted_units_rejects_other_units_as_format_error() -> None:
    spec = {"accepted_units": ["m/s^2"]}
    assert grade("9.81 m/s^2", **spec).score == 1.0
    assert grade("9.81 m/s²", **spec).score == 1.0  # same parsed unit
    result = grade("981 cm/s^2", **spec)
    assert result.score == 0.0
    assert "m/s^2" in (result.format_error or "")


# --- sig figs, feedback ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("9.81", 3),
        ("0.0098", 2),
        ("1200", 2),
        ("1200.", 4),
        ("1.200e3", 4),
        ("-3.0", 2),
        ("0", 1),
        ("0.00", 2),
        (".50", 2),
    ],
)
def test_significant_figures(number: str, expected: int) -> None:
    assert significant_figures(number) == expected


def test_sig_figs_too_few_scores_zero_with_feedback() -> None:
    result = grade("9.8 m/s^2", sig_figs=3, explanation="g near the surface.")
    assert result.score == 0.0
    assert result.format_error is None
    assert result.feedback is not None
    assert result.feedback.startswith("g near the surface.")
    assert "3 significant figures" in result.feedback
    assert grade("9.810 m/s^2", sig_figs=3).score == 1.0


def test_explanation_is_feedback_on_every_grade() -> None:
    spec = {"explanation": "g = 9.81 m/s^2."}
    assert grade("9.81 m/s^2", **spec).feedback == "g = 9.81 m/s^2."
    assert grade("5 m/s^2", **spec).feedback == "g = 9.81 m/s^2."
    assert grade("garbage", **spec).feedback == "g = 9.81 m/s^2."
    assert grade("9.81 m/s^2").feedback is None


# --- dimensionless ---------------------------------------------------------------------------


@pytest.mark.parametrize("unit", ["", "dimensionless"])
def test_pure_numbers(unit: str) -> None:
    spec = {"value": 0.5, "unit": unit}
    assert G.grade(spec, "0.5").score == 1.0  # require_unit does not apply
    assert G.grade(spec, "50 %").score == 1.0
    assert G.grade(spec, "0.7").score == 0.0
    assert G.grade(spec, "0.5 m").format_error


# --- spec checks -----------------------------------------------------------------------------


def test_good_specs_have_no_issues() -> None:
    assert G.check_spec(ACCEL) == []
    assert G.check_spec({"value": 1, "unit": "", "tolerance": {"absolute": 0.1}}) == []
    assert G.check_spec({**ACCEL, "accepted_units": ["cm/s^2"], "sig_figs": 4}) == []


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"unit": "furlongs-ish"}, "unknown_unit"),
        ({"accepted_units": ["zz"]}, "unknown_accepted_unit"),
        ({"accepted_units": ["m"]}, "accepted_unit_dimension"),
        ({"accepted_units": []}, "no_accepted_units"),
        ({"tolerance": {"relative": -0.1}}, "negative_tolerance"),
        ({"tolerance": {}}, "no_tolerance"),
        ({"tolerance": {"relative": 0, "absolute": 0}}, "no_tolerance"),
        ({"sig_figs": 0}, "bad_sig_figs"),
        ({"bogus": 1}, "invalid_spec"),
        ({"value": "nine"}, "invalid_spec"),
    ],
)
def test_check_spec_issues(extra: dict[str, Any], code: str) -> None:
    assert code in codes({**ACCEL, **extra})


def test_check_spec_missing_value() -> None:
    assert codes({"unit": "N"}) == {"invalid_spec"}


@pytest.mark.parametrize(
    "spec",
    [
        {"unit": "N"},
        {**ACCEL, "unit": "furlongs-ish"},
        {**ACCEL, "tolerance": {"absolute": -1}},
        {**ACCEL, "extra": True},
    ],
)
def test_broken_spec_raises_spec_error(spec: dict[str, Any]) -> None:
    with pytest.raises(SpecError):
        G.grade(spec, "9.81 m/s^2")


# --- registry --------------------------------------------------------------------------------


def test_build_and_registry() -> None:
    (grader,) = build(lambda: None)  # type: ignore[arg-type,return-value]
    assert grader.capability == "quantity.units" and grader.version == "1"
    assert isinstance(grader, graders.Grader)
    graders.set_executor(None)
    try:
        assert graders.get_grader("quantity.units").grade(ACCEL, "981 cm/s^2").score == 1.0
    finally:
        graders.set_executor(None)
