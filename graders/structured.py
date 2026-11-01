"""Structured-answer graders: ``structured.choice`` and ``structured.ordering`` (C1).

Answer conventions are the ones ``app/adaptive/scoring.py`` uses today, so moving a question type
onto these graders does not change any score:

- **choice**: the chosen option index as text (``"2"``); for a multi-correct question, the chosen
  indices separated by commas and/or whitespace (``"0,2"``). A spec may instead ask for the
  option's text (``answer_by="text"``), which is how a true/false question is answered.
- **ordering** (Parsons): one block id per line, leading whitespace giving the indent level in
  multiples of four spaces (a tab is one level); or, on a single line, a comma-separated list of
  ids, all at indent 0.

Every grade carries the spec's ``explanation`` (when it has text) as feedback.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr

from graders.core import Grader, GradeResult, SpecError, SpecIssue, parse_spec
from graders.executors.base import Executor


def _feedback(explanation: str | None) -> str | None:
    """The author's explanation, or ``None`` when it is blank (as the app does today)."""
    return explanation if explanation is not None and explanation.strip() else None


def _issues_or_parse_error(
    model: type[BaseModel], spec: Mapping[str, Any], check: Callable[[Any], list[SpecIssue]]
) -> list[SpecIssue]:
    try:
        parsed = parse_spec(model, spec)
    except SpecError as error:
        return [SpecIssue("invalid_spec", str(error))]
    return check(parsed)


def _raise_if_blocking(issues: list[SpecIssue], blocking: frozenset[str]) -> None:
    fatal = [issue for issue in issues if issue.code in blocking]
    if fatal:
        raise SpecError("; ".join(issue.message for issue in fatal))


# --------------------------------------------------------------------------- structured.choice


class ChoiceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    options: list[StrictStr]
    #: Indices of the correct options; one for single-answer, several for multi-correct.
    correct: list[StrictInt]
    #: ``"index"``: the answer is option indices (multiple choice). ``"text"``: the answer is
    #: one option's text, compared after stripping and case folding (true/false).
    answer_by: Literal["index", "text"] = "index"
    explanation: str | None = None


_SEPARATORS = re.compile(r"[,\s]+")


class ChoiceGrader:
    capability = "structured.choice"
    version = "1"
    spec_model = ChoiceSpec

    #: Issues that make an answer impossible to mark (``grade`` raises on these).
    _BLOCKING = frozenset({"no_correct_option", "correct_out_of_range"})

    def _check(self, spec: ChoiceSpec) -> list[SpecIssue]:
        issues: list[SpecIssue] = []
        if len(spec.options) < 2:
            issues.append(SpecIssue("too_few_options", "A choice needs at least two options."))
        for index, option in enumerate(spec.options):
            if not option.strip():
                issues.append(SpecIssue("empty_option", f"Option {index} has no text."))
        if not spec.correct:
            issues.append(SpecIssue("no_correct_option", "No correct option is recorded."))
        for index in spec.correct:
            if not 0 <= index < len(spec.options):
                issues.append(
                    SpecIssue(
                        "correct_out_of_range",
                        f"Correct option {index} is not among the {len(spec.options)} options.",
                    )
                )
        if len(set(spec.correct)) != len(spec.correct):
            issues.append(SpecIssue("duplicate_correct", "A correct option index is listed twice."))
        if spec.answer_by == "text":
            if len(spec.correct) > 1:
                issues.append(
                    SpecIssue(
                        "text_answer_multi_correct",
                        "An answer given as option text can name only one option.",
                    )
                )
            folded = [option.strip().casefold() for option in spec.options]
            if len(set(folded)) != len(folded):
                issues.append(
                    SpecIssue(
                        "ambiguous_option_text",
                        "Two options have the same text, so a text answer is ambiguous.",
                    )
                )
        return issues

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        return _issues_or_parse_error(ChoiceSpec, spec, self._check)

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        parsed = parse_spec(ChoiceSpec, spec)
        assert isinstance(parsed, ChoiceSpec)
        _raise_if_blocking(self._check(parsed), self._BLOCKING)
        feedback = _feedback(parsed.explanation)

        if parsed.answer_by == "text":
            submitted = answer.strip().casefold()
            folded = [option.strip().casefold() for option in parsed.options]
            if submitted not in folded:
                return GradeResult(
                    score=0.0,
                    feedback=feedback,
                    format_error="The answer is not one of the options.",
                )
            correct = folded.index(submitted) in parsed.correct
            return GradeResult(score=1.0 if correct else 0.0, feedback=feedback)

        if len(parsed.correct) == 1:
            try:
                chosen = int(answer.strip())
            except ValueError:
                return GradeResult(
                    score=0.0, feedback=feedback, format_error="The answer is not an option index."
                )
            correct = chosen == parsed.correct[0]
            return GradeResult(score=1.0 if correct else 0.0, feedback=feedback)

        tokens = [token for token in _SEPARATORS.split(answer.strip()) if token]
        try:
            chosen_set = {int(token) for token in tokens}
        except ValueError:
            return GradeResult(
                score=0.0, feedback=feedback, format_error="The answer is not a list of indices."
            )
        if not chosen_set:
            return GradeResult(score=0.0, feedback=feedback, format_error="No option was chosen.")
        correct = chosen_set == set(parsed.correct)
        return GradeResult(score=1.0 if correct else 0.0, feedback=feedback)


# ------------------------------------------------------------------------- structured.ordering


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: StrictStr
    indent: StrictInt = 0


class OrderingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocks: list[Block]
    correct_order: list[StrictStr]
    check_indent: bool = True
    explanation: str | None = None


def _parsons_order(answer: str) -> list[str]:
    separated = answer.replace(",", "\n")
    return [line.strip() for line in separated.splitlines() if line.strip()]


def parse_layout(answer: str) -> list[tuple[str, int]]:
    """Read block ids and indent levels from an answer, exactly as the app does today."""
    if "," in answer and "\n" not in answer and "\r" not in answer:
        return [(block_id, 0) for block_id in _parsons_order(answer)]

    layout: list[tuple[str, int]] = []
    for raw_line in answer.splitlines():
        if not raw_line.strip():
            continue
        expanded = raw_line.replace("\t", "    ")
        stripped = expanded.lstrip(" ")
        leading_spaces = len(expanded) - len(stripped)
        layout.append((stripped.strip(), leading_spaces // 4))
    return layout


class OrderingGrader:
    capability = "structured.ordering"
    version = "1"
    spec_model = OrderingSpec

    _BLOCKING = frozenset({"no_blocks", "empty_order", "unknown_block", "negative_indent"})

    @staticmethod
    def _expected(spec: OrderingSpec) -> list[tuple[str, int]]:
        # Last block wins on a duplicate id, as today.
        indents = {block.id: block.indent for block in spec.blocks}
        return [(block_id, indents[block_id]) for block_id in spec.correct_order]

    @staticmethod
    def _matches(spec: OrderingSpec, answer: str) -> bool:
        submitted = parse_layout(answer)
        expected = OrderingGrader._expected(spec)
        if spec.check_indent:
            return submitted == expected
        return [block_id for block_id, _ in submitted] == [block_id for block_id, _ in expected]

    def _check(self, spec: OrderingSpec) -> list[SpecIssue]:
        issues: list[SpecIssue] = []
        if not spec.blocks:
            issues.append(SpecIssue("no_blocks", "No blocks are recorded."))
        if not spec.correct_order:
            issues.append(SpecIssue("empty_order", "No correct block order is recorded."))
        ids = [block.id for block in spec.blocks]
        seen: set[str] = set()
        for block_id in ids:
            if block_id in seen:
                issues.append(SpecIssue("duplicate_block", f"Block id {block_id!r} is used twice."))
            seen.add(block_id)
        for block in spec.blocks:
            if block.indent < 0:
                issues.append(
                    SpecIssue("negative_indent", f"Block {block.id!r} has a negative indent.")
                )
        for block_id in spec.correct_order:
            if block_id not in seen:
                issues.append(
                    SpecIssue(
                        "unknown_block", f"The correct order names unknown block {block_id!r}."
                    )
                )
        if issues:
            return issues

        # The reference answer, written the way a student would, must score full marks. It
        # cannot when an id carries surrounding whitespace, a line break, or (alone) a comma.
        reference = "\n".join(
            "    " * indent + block_id for block_id, indent in self._expected(spec)
        )
        if not self._matches(spec, reference):
            issues.append(
                SpecIssue(
                    "reference_not_full_marks",
                    "The correct order, written as an answer, does not score full marks "
                    "(a block id has surrounding whitespace, a line break or a comma).",
                )
            )
        return issues

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        return _issues_or_parse_error(OrderingSpec, spec, self._check)

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        parsed = parse_spec(OrderingSpec, spec)
        assert isinstance(parsed, OrderingSpec)
        _raise_if_blocking(self._check(parsed), self._BLOCKING)
        feedback = _feedback(parsed.explanation)
        if not parse_layout(answer):
            return GradeResult(score=0.0, feedback=feedback, format_error="No blocks were given.")
        return GradeResult(score=1.0 if self._matches(parsed, answer) else 0.0, feedback=feedback)


def build(executor_factory: Callable[[], Executor]) -> list[Grader]:
    del executor_factory  # these graders run no code
    return [ChoiceGrader(), OrderingGrader()]
