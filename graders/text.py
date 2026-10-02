"""``text.normalized_match``: the answer equals the expected text after normalisation (C1).

Normalised exactly as ``app/validation/runner.py::normalize_output`` compares a program's stdout
today: CRLF and CR become LF, then at most one trailing newline is removed. Case folding and
whitespace collapsing are opt-in and off by default.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr

from graders.core import Grader, GradeResult, SpecError, SpecIssue, parse_spec
from graders.executors.base import Executor


class NormalizedMatchSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected: StrictStr
    fold_case: bool = False
    #: Every run of whitespace (line breaks included) becomes one space; ends are trimmed.
    collapse_whitespace: bool = False
    explanation: str | None = None


def normalize(text: str, *, fold_case: bool = False, collapse_whitespace: bool = False) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").removesuffix("\n")
    if fold_case:
        normalized = normalized.casefold()
    if collapse_whitespace:
        normalized = " ".join(normalized.split())
    return normalized


class NormalizedMatchGrader:
    capability = "text.normalized_match"
    version = "1"
    spec_model = NormalizedMatchSpec

    def check_spec(self, spec: Mapping[str, Any]) -> list[SpecIssue]:
        try:
            parse_spec(NormalizedMatchSpec, spec)
        except SpecError as error:
            return [SpecIssue("invalid_spec", str(error))]
        # The expected text always matches itself, so a well-formed spec is gradable.
        return []

    def grade(self, spec: Mapping[str, Any], answer: str) -> GradeResult:
        parsed = parse_spec(NormalizedMatchSpec, spec)
        assert isinstance(parsed, NormalizedMatchSpec)
        explanation = parsed.explanation
        feedback = explanation if explanation is not None and explanation.strip() else None
        options = {
            "fold_case": parsed.fold_case,
            "collapse_whitespace": parsed.collapse_whitespace,
        }
        correct = normalize(answer, **options) == normalize(parsed.expected, **options)
        return GradeResult(score=1.0 if correct else 0.0, feedback=feedback)


def build(executor_factory: Callable[[], Executor]) -> list[Grader]:
    del executor_factory  # this grader runs no code
    return [NormalizedMatchGrader()]
