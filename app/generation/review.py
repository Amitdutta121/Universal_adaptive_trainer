"""Judge a round question inside the retry loop (docs/QUESTION_SETUP_PLAN.md, step 4).

Outside a round, judges are advisory and run once after generation. A round is aimed at a
(subtopic, difficulty, style) cell, so a question the judges place elsewhere is not a
question for that cell: the reason goes back to the generator as a correction, and after
the last attempt the question is dropped. This module turns one judge pass into the failed
checks :func:`~app.generation.attempts.generate_with_retries` feeds back.

Round questions require every requested check to pass. An unavailable judge is not
evidence of a wrong question, but it cannot certify a question for this round either.

A duplicate of a stored question (ADR-063 point 6) is the one exception to "drop what still
fails": it is retried like any failed check, but on the last attempt it is judged and kept,
with a similarity flag for the professor. The duplicate check itself is injected
(:data:`DuplicateCheck`), because finding one needs embeddings and ``app.generation`` must
not import ``app.retrieval``.

A question only *resembling* a stored one (the soft band below the duplicate line) can still
be the same idea reworded. For the nearest such match one cheap structured call
(:class:`ConceptChecker`, injected as :data:`ConceptCheck`) asks whether both assess the same
concept in the same way; "yes" is retried like a duplicate, and on the last attempt the
question is kept, flagged and held for review. Without a model the check is skipped.

A multiple-choice or true/false question is also solved blind by other models
(:mod:`app.generation.solve`, injected as :data:`BlindSolve`). A solver that disagrees with
the key is a correction for the next attempt; on the last attempt the question is kept,
flagged and held for review, because one solver in about thirty disagrees with a good key.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Protocol

from pydantic import BaseModel, Field

from app.domain.enums import JudgeMetricId
from app.domain.questions import Question, QuestionCheck
from app.evaluation import MetricStatus, PedagogicalEvaluation, PedagogicalJudge
from app.evaluation import custom as custom_judges
from app.evaluation.custom import CustomJudgeResult, CustomRule
from app.evaluation.severity import (
    borderline_notes,
    difficulty_is_clear,
    issues_are_clear,
    subtopic_is_clear,
)
from app.generation.attempts import MAX_GENERATION_ATTEMPTS
from app.generation.solve import BlindSolve, student_view
from app.generation.spec import QuestionSpec
from app.llm import StructuredLLMClient, get_structured_client

logger = logging.getLogger(__name__)

#: Check names, as they appear on an attempt's ``failed_checks`` and in the correction.
TARGET_SUBTOPIC_CHECK = "target_subtopic"
DIFFICULTY_JUDGE_CHECK = "difficulty_judge"
TOPIC_JUDGE_CHECK = "topic_judge"
ISSUES_JUDGE_CHECK = "issues_judge"
CUSTOM_RULE_CHECK = "custom_rule"
DUPLICATE_CHECK = "duplicate"
SAME_CONCEPT_CHECK = "same_concept"
BLIND_SOLVE_CHECK = "blind_solve"

#: How much of the duplicate's text the correction quotes.
DUPLICATE_QUOTE_CHARS = 400


class SimilarMatch(Protocol):
    """A stored question the new one resembles (``app.retrieval.duplicates.SimilarQuestion``)."""

    @property
    def question_id(self) -> int: ...
    @property
    def text(self) -> str: ...
    @property
    def score(self) -> float: ...
    @property
    def model(self) -> str: ...
    @property
    def duplicate(self) -> bool:
        """Too close to keep without a retry."""
        ...


#: Returns the stored questions an unsaved question resembles, best first; empty when none.
DuplicateCheck = Callable[[Question], Sequence[SimilarMatch]]


class SameConceptVerdict(BaseModel):
    """Do two questions assess the same concept in the same way?"""

    same: bool = Field(description="True when both assess the same concept in the same way.")
    reason: str = Field(description="One sentence: why.")


#: Asks whether an unsaved question assesses the same idea as a resembled stored one;
#: ``None`` when it could not tell (no model, a provider failure).
ConceptCheck = Callable[[Question, SimilarMatch], SameConceptVerdict | None]

CONCEPT_SYSTEM = (
    "You compare two assessment questions. Answer same=true only if a student who can answer "
    "one could answer the other with the same knowledge and the same reasoning -- the same "
    "concept assessed the same way, merely reworded or with trivially different values. "
    "Different aspects, skills or misconceptions of one topic are not the same."
)


def _question_text(question: Question) -> str:
    """Prompt, code and options, as the duplicate check compares them."""
    content = question.content or {}
    parts = [question.prompt or ""]
    if content.get("code"):
        parts.append(str(content["code"]))
    if isinstance(content.get("options"), list):
        parts.extend(str(option) for option in content["options"])
    return "\n".join(parts)


class ConceptChecker:
    """The :data:`ConceptCheck` of a round: one structured call per soft-band match.

    Never raises: without a configured model, or on any provider failure, it answers
    ``None`` and the question is treated as merely similar.
    """

    def __init__(self, client: StructuredLLMClient | None = None) -> None:
        self._client = client

    def __call__(self, question: Question, match: SimilarMatch) -> SameConceptVerdict | None:
        try:
            llm = self._client or get_structured_client()
            return llm.complete_structured(
                system=CONCEPT_SYSTEM,
                prompt=(
                    f"Question 1 (new):\n{_question_text(question)[: DUPLICATE_QUOTE_CHARS * 2]}"
                    "\n\nQuestion 2 (already in the bank):\n"
                    f"{match.text[: DUPLICATE_QUOTE_CHARS * 2]}\n\n"
                    "Do these two questions assess the same concept in the same way?"
                ),
                response_model=SameConceptVerdict,
            )
        except Exception:
            logger.warning("concept check skipped", exc_info=True)
            return None


_BAND_HINTS = {
    "easy": "one taught step, applied directly.",
    "medium": "two taught ideas combined, or one idea applied to an ordinary new case.",
    "hard": "three or more taught ideas composed, or reasoning about an edge case.",
}


def _band_hint(difficulty: str) -> str:
    return _BAND_HINTS.get(difficulty, "")


def _failed(name: str, detail: str, evidence: str | None = None) -> QuestionCheck:
    return QuestionCheck(
        name=name, passed=False, deterministic=False, detail=detail, evidence=evidence
    )


class RoundReview:
    """The ``review`` hook for one round target; remembers its last judge pass.

    The generator calls it on every clean attempt. The evaluation and custom results of the
    last call are kept so the stored question carries the judgement that passed it, without
    paying for a second judge run.
    """

    def __init__(
        self,
        judge: PedagogicalJudge,
        rules: Sequence[CustomRule],
        *,
        spec: QuestionSpec,
        client: StructuredLLMClient | None = None,
        duplicates: DuplicateCheck | None = None,
        concepts: ConceptCheck | None = None,
        solver: BlindSolve | None = None,
        max_attempts: int = MAX_GENERATION_ATTEMPTS,
    ) -> None:
        if spec.target_subtopic_id is None:
            raise ValueError("RoundReview needs a round spec (target_subtopic_id set).")
        self._judge = judge
        self._rules = list(rules)
        self._spec = spec
        self._target = spec.target_subtopic_id
        self._client = client
        self._duplicates = duplicates
        self._concepts = concepts
        self._solver = solver
        self._max_attempts = max_attempts
        self.last_evaluation: PedagogicalEvaluation | None = None
        self.last_custom: list[CustomJudgeResult] = []
        #: Stored questions the last reviewed attempt resembles; flagged when it is kept.
        self.last_similar: list[SimilarMatch] = []
        #: The soft-band match the last attempt assesses the same idea as; held when kept.
        self.last_same_concept: SimilarMatch | None = None
        #: Last judge-failed draft, so a later passing attempt can still leave an audit (m9).
        self.last_failed_question: Question | None = None
        self.last_failed_evaluation: PedagogicalEvaluation | None = None
        #: Borderline judge notes on a kept attempt (m10).
        self.last_notes: list[str] = []
        #: What the blind solvers said against the key of a kept last attempt; held when set.
        self.last_solve_flag: str | None = None

    def __call__(self, question: Question) -> list[QuestionCheck]:
        self.last_evaluation = None
        self.last_custom = []
        self.last_similar = []
        self.last_same_concept = None
        self.last_notes = []
        self.last_solve_flag = None
        number = question.generation_attempts[-1].number if question.generation_attempts else 1

        # The generator's own claim must name the target before any judge is paid for.
        if self._target not in question.subtopic_ids:
            return [
                _failed(
                    TARGET_SUBTOPIC_CHECK,
                    f"it does not list the target subtopic {self._target} in subtopic_ids",
                    f"Write a question that assesses subtopic {self._target} and include "
                    f"{self._target} in subtopic_ids.",
                )
            ]

        # Before the judges: a duplicate is retried anyway, so judging it would be wasted.
        if self._duplicates is not None:
            self.last_similar = list(self._duplicates(question))
            duplicate = next((match for match in self.last_similar if match.duplicate), None)
            if duplicate is not None and number < self._max_attempts:
                return [
                    _failed(
                        DUPLICATE_CHECK,
                        f"it is too similar to: {duplicate.text[:DUPLICATE_QUOTE_CHARS]}",
                        "Write a question that asks something different, not the same "
                        "question reworded.",
                    )
                ]
            nearest = next((match for match in self.last_similar if not match.duplicate), None)
            if duplicate is None and nearest is not None and self._concepts is not None:
                verdict = self._concepts(question, nearest)
                if verdict is not None and verdict.same:
                    self.last_same_concept = nearest
                    if number < self._max_attempts:
                        return [
                            _failed(
                                SAME_CONCEPT_CHECK,
                                "it assesses the same idea as: "
                                f"{nearest.text[:DUPLICATE_QUOTE_CHARS]}",
                                f"{verdict.reason} Assess a different idea or a different "
                                "way of using it, not the same question reworded.",
                            )
                        ]

        failed: list[QuestionCheck] = []
        evaluation = self._judge.evaluate(question)
        self.last_evaluation = evaluation

        difficulty = evaluation.metric(JudgeMetricId.DIFFICULTY)
        if (
            difficulty is None
            or difficulty.status is not MetricStatus.COMPLETED
            or (
                difficulty.passed is not True
                and difficulty.proposed_difficulty in (None, self._spec.difficulty)
            )
        ):
            failed.append(
                _failed(
                    DIFFICULTY_JUDGE_CHECK,
                    "the difficulty reviewer could not confirm the requested level",
                    f"Make the question unmistakably {self._spec.difficulty.value}: "
                    f"{_band_hint(self._spec.difficulty.value)}",
                )
            )
        elif (
            difficulty.passed is not True
            and difficulty.proposed_difficulty is not None
            and difficulty.proposed_difficulty is not self._spec.difficulty
        ):
            wanted = self._spec.difficulty.value
            if difficulty_is_clear(self._spec.difficulty, difficulty.proposed_difficulty):
                failed.append(
                    _failed(
                        DIFFICULTY_JUDGE_CHECK,
                        f"a reviewer rated it {difficulty.proposed_difficulty.value}, "
                        f"but it must be {wanted}",
                        f"Reviewer: {difficulty.rationale or 'no rationale'} "
                        f"Make the question genuinely {wanted}.",
                    )
                )

        topic = evaluation.metric(JudgeMetricId.SUBTOPIC)
        proposed_ids = list(topic.proposed_subtopic_ids or []) if topic is not None else []
        if (
            topic is None
            or topic.status is not MetricStatus.COMPLETED
            or (topic.passed is not True and not proposed_ids)
        ):
            failed.append(
                _failed(
                    TOPIC_JUDGE_CHECK,
                    "the topic reviewer could not confirm the target subtopic",
                    f"Make it unmistakable that answering requires subtopic {self._target}, "
                    "not only incidental use of it.",
                )
            )
        elif topic.passed is not True and subtopic_is_clear(self._target, proposed_ids):
            failed.append(
                _failed(
                    TOPIC_JUDGE_CHECK,
                    f"a reviewer says it assesses subtopic(s) {proposed_ids}, "
                    f"not the target subtopic {self._target}",
                    f"Reviewer: {topic.rationale or 'no rationale'} "
                    f"Make the question clearly assess subtopic {self._target}.",
                )
            )

        issues = evaluation.metric(JudgeMetricId.ISSUES)
        if (
            issues is not None
            and issues.status is MetricStatus.COMPLETED
            and issues.passed is False
            and issues_are_clear(issues.issue_codes)
        ):
            failed.append(
                _failed(
                    ISSUES_JUDGE_CHECK,
                    "the issues judge found a blocking defect",
                    issues.rationale or "Fix the incorrect answer, tests, or technical error.",
                )
            )

        if self._solver is not None:
            findings = self._solver(question)
            view = student_view(question) if findings else None
            if view is not None:
                said = "; ".join(finding.describe(view[1]) for finding in findings)
                if number < self._max_attempts:
                    failed.append(
                        _failed(
                            BLIND_SOLVE_CHECK,
                            "another model, answering without the key, disagrees with it",
                            f"{said} Fix it by correcting the key, making the other options "
                            "clearly wrong, or adding the missing information. Keep the "
                            "concept and the difficulty.",
                        )
                    )
                else:
                    self.last_solve_flag = said

        self.last_notes = borderline_notes(
            evaluation,
            requested_difficulty=self._spec.difficulty,
            target_subtopic_id=self._target,
        )

        if self._rules:
            # Looked up on the module so the owner's implementation (and test fakes) apply.
            self.last_custom = custom_judges.run_custom_judges(
                question, self._rules, client=self._client
            )
            for result in self.last_custom:
                if result.passed is not True:
                    failed.append(
                        _failed(
                            CUSTOM_RULE_CHECK,
                            f'the professor\'s rule "{result.rule_text}" did not pass',
                            result.reason,
                        )
                    )
            answered = {result.judge_id for result in self.last_custom}
            for rule in self._rules:
                if rule.id not in answered:
                    failed.append(
                        _failed(CUSTOM_RULE_CHECK, f'no result for rule "{rule.rule_text}"')
                    )
        if failed and any(
            check.name in (DIFFICULTY_JUDGE_CHECK, TOPIC_JUDGE_CHECK) for check in failed
        ):
            self.last_failed_question = question.model_copy(deep=True)
            self.last_failed_evaluation = evaluation
        return failed
