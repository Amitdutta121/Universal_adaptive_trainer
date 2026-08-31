"""Question entities and validation reports.

Two invariants are encoded here because both the professor pipeline and the
student engine depend on them:

1. A question always remembers the text that was *generated*, even after the
   professor edits it (``original_*`` fields; see :func:`apply_professor_edit`).
2. A question records which generator produced it, by kind *and* version, so
   base and personalized generators stay distinguishable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import (
    ClaimViolation,
    Difficulty,
    GeneratorKind,
    QuestionKind,
    QuestionStatus,
    QuestionType,
)

#: Priority given to a question that has just been served. Lower is served later;
#: the adaptive engine picks the highest-priority candidate for a subtopic and
#: difficulty, so a used question sinks to the back of the queue.
LOWEST_PRIORITY = 0

#: Priority assigned to a freshly approved, never-served question.
DEFAULT_PRIORITY = 100


def _now() -> datetime:
    return datetime.now(UTC)


class QuestionCheck(BaseModel):
    """One deterministic or LLM check performed on a question."""

    name: str = Field(min_length=1)
    passed: bool
    #: Deterministic checks (syntax, execution, tests) outrank LLM judgment.
    deterministic: bool = True
    severity: Literal["error"] = "error"
    detail: str | None = None
    evidence: str | None = None


class QuestionValidationReport(BaseModel):
    """Outcome of validating a single question."""

    question_id: int | None = None
    checks: list[QuestionCheck] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)

    @property
    def deterministic_checks(self) -> list[QuestionCheck]:
        return [c for c in self.checks if c.deterministic]

    @property
    def passed(self) -> bool:
        """A report passes only if every deterministic check passed.

        A failing deterministic check cannot be overridden by a positive LLM
        judgment; if there are no deterministic checks at all, the report does
        not pass.
        """
        deterministic = self.deterministic_checks
        if not deterministic:
            return False
        return all(check.passed for check in deterministic)

    def resulting_status(self) -> QuestionStatus:
        return QuestionStatus.VALIDATION_PASSED if self.passed else QuestionStatus.VALIDATION_FAILED


class GenerationAttempt(BaseModel):
    """One model call that tried to produce this question (ADR-032).

    A question that took three attempts is one question with three attempts, not
    three questions: separate rows would fill the bank with drafts that every
    later query would have to learn to exclude, and the adaptive engine has no
    use for a draft that was never valid.

    The claim is recorded as the model made it, duplicates and non-existent ids
    included, because it is the evidence for how this generator fails. What
    actually reached the columns is narrower -- see
    :class:`~app.generation.spec.TaxonomyClaimOutcome`.
    """

    number: int = Field(ge=1)
    #: ``None`` when the reply could not be read as a question at all, so there
    #: was no claim to record. See :attr:`malformed`.
    claimed_topic_id: int | None = None
    claimed_subtopic_ids: list[int] = Field(default_factory=list)
    violations: list[ClaimViolation] = Field(default_factory=list)
    #: The refusal in one sentence, as it was put back to the model on retry.
    detail: str | None = None
    #: Deterministic checks this attempt failed. A retry is triggered by either a
    #: refused claim or a failed check, so without these an attempts table would
    #: show three accepted claims and no reason the first two were rejected.
    failed_checks: list[QuestionCheck] = Field(default_factory=list)
    #: The model answered with something that was not a question -- most often the
    #: schema of the draft rather than an instance of it. Recorded rather than
    #: swallowed: ADR-020 objects to bad answers being *silently* re-prompted, not
    #: to them being retried.
    malformed: bool = False
    accepted: bool
    #: Provenance of the call, so a claim can be read against the model that made it.
    model: str | None = None

    @property
    def usable(self) -> bool:
        """Whether this attempt was good enough to stop retrying."""
        return self.accepted and not self.failed_checks and not self.malformed


class Question(BaseModel):
    """An assessment question grounded in approved curriculum subtopics."""

    model_config = ConfigDict(from_attributes=True)

    id: int | None = None

    # Grounding: which approved curriculum this question belongs to.
    curriculum_version_id: int | None = None
    topic_id: int | None = None
    #: Every subtopic the question exercises, as claimed by the generator and
    #: checked by the subtopic judge. Plural because one question can exercise
    #: several subtopics of its topic, and a student's score updates the
    #: weakness of each of them.
    subtopic_ids: list[int] = Field(default_factory=list)

    kind: QuestionKind = QuestionKind.TESTABLE_PROGRAM
    question_type: QuestionType | None = None
    difficulty: Difficulty = Difficulty.EASY
    status: QuestionStatus = QuestionStatus.GENERATED

    prompt: str = Field(min_length=1)
    reference_solution: str | None = None
    #: Serialized test cases for ``TESTABLE_PROGRAM`` questions. Kept opaque
    #: (text) at this stage; the executable format is decided with the validator.
    tests: str | None = None

    #: Frozen generation request (a dumped ``QuestionSpec``) for later comparison.
    spec: dict[str, Any] | None = None
    #: Full typed draft plus grounding metadata for display and scoring.
    content: dict[str, Any] | None = None
    #: Deterministic validation outcome, for display and review.
    validation_report: QuestionValidationReport | None = None
    #: Every model call that tried to produce this question, oldest first. Empty
    #: for questions generated before ADR-032, which is what
    #: :mod:`app.validation` reads to leave those reports unchanged.
    generation_attempts: list[GenerationAttempt] = Field(default_factory=list)
    #: LLM pedagogical evaluation. Left as a plain object because its shape is
    #: owned by :mod:`app.evaluation`, which the domain must not import.
    pedagogical_eval: dict[str, Any] | None = None
    personalization_context: dict[str, Any] | None = None

    # Retained generated originals. Never overwritten by professor edits.
    original_prompt: str | None = None
    original_reference_solution: str | None = None
    original_tests: str | None = None

    # Provenance.
    generator_kind: GeneratorKind = GeneratorKind.BASE
    generator_name: str = "unset"
    generator_version: str = "0"
    #: Set when an instructor regenerated this question from another one with
    #: feedback (a new row, never an edit of the source).
    regenerated_from_question_id: int | None = None
    regeneration_feedback: str | None = None

    #: Selection priority; lowered to :data:`LOWEST_PRIORITY` once served.
    priority: int = DEFAULT_PRIORITY
    times_used: int = Field(default=0, ge=0)

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _seed_originals(self) -> Question:
        """Capture the generated text as the original on first construction."""
        if self.original_prompt is None:
            self.original_prompt = self.prompt
        if self.original_reference_solution is None and self.reference_solution is not None:
            self.original_reference_solution = self.reference_solution
        if self.original_tests is None and self.tests is not None:
            self.original_tests = self.tests
        return self

    @property
    def was_edited_by_professor(self) -> bool:
        return (
            self.prompt != self.original_prompt
            or self.reference_solution != self.original_reference_solution
            or self.tests != self.original_tests
        )


def apply_professor_edit(
    question: Question,
    *,
    prompt: str | None = None,
    reference_solution: str | None = None,
    tests: str | None = None,
) -> Question:
    """Return a copy of ``question`` with professor edits applied.

    The ``original_*`` fields are preserved untouched, which is what makes
    "generated vs. accepted" comparisons possible for later generator
    optimization.
    """
    updates: dict[str, object] = {"updated_at": _now()}
    if prompt is not None:
        updates["prompt"] = prompt
    if reference_solution is not None:
        updates["reference_solution"] = reference_solution
    if tests is not None:
        updates["tests"] = tests
    return question.model_copy(update=updates)
