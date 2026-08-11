"""Deterministic checks for each supported assessment format."""

from __future__ import annotations

import ast
from collections.abc import Callable

from pydantic import ValidationError

from app.domain.enums import QuestionType
from app.domain.questions import Question, QuestionCheck
from app.generation.schemas import ExecutableTestCase
from app.validation.report import make_check
from app.validation.runner import EVIDENCE_LIMIT, LocalCodeRunner, TestRunSummary, normalize_output


def check_type(
    question: Question,
    content: dict,
    runner: LocalCodeRunner,
) -> list[QuestionCheck]:
    """Run the checks belonging to the question's assessment format."""
    if question.question_type is None:
        return []

    checker = _CHECKER_FOR[question.question_type]
    return checker(content, runner)


def _parses(source: str) -> bool:
    try:
        ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return False
    return True


def _parse_tests(raw: object) -> list[ExecutableTestCase] | None:
    if not isinstance(raw, list) or not raw:
        return None
    try:
        return [ExecutableTestCase.model_validate(case) for case in raw]
    except (ValidationError, TypeError):
        return None


def _multiple_choice(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    del runner
    options = content.get("options")
    options_valid = (
        isinstance(options, list)
        and len(options) >= 2
        and all(isinstance(option, str) and bool(option.strip()) for option in options)
    )
    no_duplicates = options_valid and len(set(options)) == len(options)
    correct_index = content.get("correct_option_index")
    correct_exists = (
        options_valid
        and isinstance(correct_index, int)
        and not isinstance(correct_index, bool)
        and 0 <= correct_index < len(options)
    )
    explanation_present = _present_text(content.get("explanation"))
    return [
        make_check("mc_options_valid", options_valid, "Options are valid"),
        make_check("mc_no_duplicate_options", no_duplicates, "No duplicate options"),
        make_check(
            "mc_correct_option_exists",
            correct_exists,
            "Correct-answer reference exists",
        ),
        make_check(
            "mc_explanation_present",
            explanation_present,
            "Explanation exists",
        ),
    ]


def _true_false(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    del runner
    return [
        make_check(
            "tf_boolean_answer",
            isinstance(content.get("correct_answer"), bool),
            "Valid boolean answer",
        ),
        make_check(
            "tf_explanation_present",
            _present_text(content.get("explanation")),
            "Explanation exists",
        ),
    ]


def _output_prediction(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    source = content.get("code")
    code_parses = isinstance(source, str) and _parses(source)
    expected = content.get("expected_output")
    output_verified = False
    evidence = None
    if code_parses and isinstance(expected, str):
        result = runner.run_script(source)
        output_verified = (
            not result.timed_out
            and result.exit_code == 0
            and normalize_output(result.stdout) == normalize_output(expected)
        )
        if not output_verified:
            evidence = _script_evidence(result, expected)
    return [
        make_check("output_code_parses", code_parses, "Prediction code parses"),
        make_check(
            "expected_output_verified",
            output_verified,
            "Expected output verified",
            evidence,
        ),
    ]


def _code_completion(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    reference = content.get("reference_solution")
    reference_parses = isinstance(reference, str) and _parses(reference)
    tests = _parse_tests(content.get("tests"))
    summary = _run_reference(reference, reference_parses, tests, runner)
    return [
        make_check(
            "completion_reference_parses",
            reference_parses,
            "Reference solution parses",
        ),
        make_check("harness_valid", tests is not None, "Test harness is valid"),
        _reference_check(summary, len(tests) if tests is not None else 0),
    ]


def _debugging(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    broken = content.get("code")
    broken_parses = isinstance(broken, str) and _parses(broken)
    reference = content.get("reference_solution")
    reference_parses = isinstance(reference, str) and _parses(reference)
    tests = _parse_tests(content.get("tests"))

    broken_exhibits_issue = not broken_parses or tests is None
    broken_evidence = None
    if broken_parses and tests is not None:
        broken_summary = runner.run_tests(broken, tests)
        broken_exhibits_issue = (
            broken_summary.passed_count < broken_summary.total
            or broken_summary.timed_out
            or any(result.exit_code not in (0, None) for result in broken_summary.results)
        )
        if broken_exhibits_issue:
            broken_evidence = broken_summary.evidence

    reference_summary = _run_reference(reference, reference_parses, tests, runner)
    return [
        make_check(
            "debug_broken_exhibits_issue",
            broken_exhibits_issue,
            "Broken code exhibits the issue",
            broken_evidence,
        ),
        make_check(
            "debug_reference_parses",
            reference_parses,
            "Reference solution parses",
        ),
        make_check("harness_valid", tests is not None, "Test harness is valid"),
        _reference_check(
            reference_summary,
            len(tests) if tests is not None else 0,
        ),
    ]


def _parsons(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    del runner
    blocks = content.get("blocks")
    order = content.get("correct_order")
    valid_blocks = (
        isinstance(blocks, list)
        and bool(blocks)
        and all(isinstance(block, dict) for block in blocks)
    )
    block_ids = [block.get("id") for block in blocks] if valid_blocks else []
    order_consistent = (
        valid_blocks
        and isinstance(order, list)
        and all(isinstance(block_id, str) for block_id in order)
        and all(isinstance(block_id, str) for block_id in block_ids)
        and len(set(block_ids)) == len(block_ids)
        and len(order) == len(block_ids)
        and len(set(order)) == len(order)
        and set(order) == set(block_ids)
    )
    indent_valid = valid_blocks and all(
        isinstance(block.get("indent"), int)
        and not isinstance(block.get("indent"), bool)
        and block["indent"] >= 0
        for block in blocks
    )

    reference_compiles = False
    evidence = None
    if order_consistent and indent_valid:
        blocks_by_id = {block["id"]: block for block in blocks}
        text_valid = all(isinstance(blocks_by_id[block_id].get("text"), str) for block_id in order)
        if text_valid:
            source = "\n".join(
                (" " * (4 * blocks_by_id[block_id]["indent"])) + blocks_by_id[block_id]["text"]
                for block_id in order
            )
            try:
                compile(source, "<parsons>", "exec")
            except (SyntaxError, TypeError, ValueError) as error:
                evidence = str(error)
            else:
                reference_compiles = True

    return [
        make_check(
            "parsons_order_consistent",
            order_consistent,
            "Canonical order is consistent",
        ),
        make_check(
            "parsons_indent_valid",
            indent_valid,
            "Indentation representation is valid",
        ),
        make_check(
            "parsons_reference_compiles",
            reference_compiles,
            "Reconstructed reference compiles",
            evidence,
        ),
    ]


def _coding(content: dict, runner: LocalCodeRunner) -> list[QuestionCheck]:
    reference = content.get("reference_solution")
    reference_parses = isinstance(reference, str) and _parses(reference)
    tests = _parse_tests(content.get("tests"))
    summary = _run_reference(reference, reference_parses, tests, runner)
    return [
        make_check(
            "coding_reference_parses",
            reference_parses,
            "Reference solution parses",
        ),
        make_check("harness_valid", tests is not None, "Test harness is valid"),
        _reference_check(summary, len(tests) if tests is not None else 0),
    ]


def _present_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _run_reference(
    reference: object,
    reference_parses: bool,
    tests: list[ExecutableTestCase] | None,
    runner: LocalCodeRunner,
) -> TestRunSummary | None:
    if not reference_parses or tests is None:
        return None
    return runner.run_tests(reference, tests)


def _reference_check(
    summary: TestRunSummary | None,
    total: int,
) -> QuestionCheck:
    passed = summary.passed_count if summary is not None else 0
    successful = summary is not None and passed == summary.total and not summary.timed_out
    evidence = summary.evidence if summary is not None else None
    return make_check(
        "reference_passes_tests",
        successful,
        f"{passed}/{total} tests pass",
        evidence,
    )


def _script_evidence(result: object, expected: str) -> str:
    if result.timed_out:
        return "Execution timed out."
    if result.exit_code != 0:
        evidence = f"Exited with code {result.exit_code}. {result.stderr}".strip()
    else:
        evidence = (
            f"stdout mismatch; expected {normalize_output(expected)!r}, "
            f"got {normalize_output(result.stdout)!r}."
        )
    return evidence[:EVIDENCE_LIMIT]


TypeChecker = Callable[[dict, LocalCodeRunner], list[QuestionCheck]]

_CHECKER_FOR: dict[QuestionType, TypeChecker] = {
    QuestionType.MULTIPLE_CHOICE: _multiple_choice,
    QuestionType.TRUE_FALSE: _true_false,
    QuestionType.OUTPUT_PREDICTION: _output_prediction,
    QuestionType.CODE_COMPLETION: _code_completion,
    QuestionType.DEBUGGING: _debugging,
    QuestionType.PARSONS: _parsons,
    QuestionType.CODING: _coding,
}
