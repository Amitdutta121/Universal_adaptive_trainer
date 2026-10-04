"""Judge a round question inside the retry loop (docs/QUESTION_SETUP_PLAN.md, step 4).

Outside a round, judges are advisory and run once after generation. A round is aimed at a
(subtopic, difficulty, style) cell, so a question the judges place elsewhere is not a
question for that cell: the reason goes back to the generator as a correction, and after
the last attempt the question is dropped. This module turns one judge pass into the failed
checks :func:`~app.generation.attempts.generate_with_retries` feeds back.

Round questions require every requested check to pass. An unavailable judge is not
evidence of a wrong question, but it cannot certify a question for this round either.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.enums import JudgeMetricId
from app.domain.questions import Question, QuestionCheck
from app.evaluation import MetricStatus, PedagogicalEvaluation, PedagogicalJudge
from app.evaluation import custom as custom_judges
from app.evaluation.custom import CustomJudgeResult, CustomRule
from app.generation.spec import QuestionSpec
from app.llm import StructuredLLMClient

#: Check names, as they appear on an attempt's ``failed_checks`` and in the correction.
TARGET_SUBTOPIC_CHECK = "target_subtopic"
DIFFICULTY_JUDGE_CHECK = "difficulty_judge"
TOPIC_JUDGE_CHECK = "topic_judge"
CUSTOM_RULE_CHECK = "custom_rule"


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
    ) -> None:
        if spec.target_subtopic_id is None:
            raise ValueError("RoundReview needs a round spec (target_subtopic_id set).")
        self._judge = judge
        self._rules = list(rules)
        self._spec = spec
        self._target = spec.target_subtopic_id
        self._client = client
        self.last_evaluation: PedagogicalEvaluation | None = None
        self.last_custom: list[CustomJudgeResult] = []

    def __call__(self, question: Question) -> list[QuestionCheck]:
        self.last_evaluation = None
        self.last_custom = []

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
                    "the difficulty check did not pass",
                    "The difficulty judge must confirm the requested level.",
                )
            )
        if (
            difficulty is not None
            and difficulty.status is MetricStatus.COMPLETED
            and difficulty.proposed_difficulty is not None
            and difficulty.proposed_difficulty is not self._spec.difficulty
        ):
            wanted = self._spec.difficulty.value
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
        if (
            topic is None
            or topic.status is not MetricStatus.COMPLETED
            or (
                topic.passed is not True
                and self._target in (topic.proposed_subtopic_ids or question.subtopic_ids)
            )
        ):
            failed.append(
                _failed(
                    TOPIC_JUDGE_CHECK,
                    "the topic check did not pass",
                    "The topic judge must confirm the target subtopic.",
                )
            )
        if (
            topic is not None
            and topic.status is MetricStatus.COMPLETED
            and self._target not in (topic.proposed_subtopic_ids or question.subtopic_ids)
        ):
            failed.append(
                _failed(
                    TOPIC_JUDGE_CHECK,
                    f"a reviewer says it assesses subtopic(s) {topic.proposed_subtopic_ids}, "
                    f"not the target subtopic {self._target}",
                    f"Reviewer: {topic.rationale or 'no rationale'} "
                    f"Make the question clearly assess subtopic {self._target}.",
                )
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
        return failed
