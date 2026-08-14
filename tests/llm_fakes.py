"""Fake structured clients for generation and for the four metric judges.

Shared so every test that needs a generated or judged question builds one the
same way; a per-file fake would drift from the real shapes one file at a time.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.domain.enums import Difficulty, JudgeMetricId, RejectionReason
from app.errors import MalformedModelOutputError
from app.evaluation.schema import (
    DifficultyVerdict,
    GeneratabilityVerdict,
    IssuesVerdict,
    MetricResult,
    PedagogicalEvaluation,
    SubtopicVerdict,
    evaluation_from_metrics,
    failed_metric,
)
from app.generation.schemas import TaxonomyClaim


def metric_results(
    *, failing: set[JudgeMetricId] | None = None, missing: set[JudgeMetricId] | None = None
) -> list[MetricResult]:
    """Four metric results, all passing unless named in ``failing``/``missing``."""
    failing = failing or set()
    missing = missing or set()
    results = []
    for metric in JudgeMetricId:
        if metric in missing:
            results.append(failed_metric(metric, detail="reviewer unavailable"))
        else:
            results.append(
                MetricResult(metric=metric, passed=metric not in failing, rationale="because")
            )
    return results


def judged(
    *,
    question_id: int | None = None,
    failing: set[JudgeMetricId] | None = None,
    missing: set[JudgeMetricId] | None = None,
    judge_model: str = "fake/judge-model",
) -> PedagogicalEvaluation:
    """A stored evaluation, approved by default."""
    return evaluation_from_metrics(
        metric_results(failing=failing, missing=missing),
        question_id=question_id,
        judge_model=judge_model,
    )


def verdict_for(
    response_model: type[BaseModel],
    topic_id: int,
    subtopic_ids: list[int],
    *,
    difficulty: Difficulty = Difficulty.EASY,
) -> BaseModel:
    """The agreeing verdict for one metric, for hand-rolled fake clients."""
    if response_model is IssuesVerdict:
        return IssuesVerdict(rationale="sound")
    if response_model is SubtopicVerdict:
        return SubtopicVerdict(
            topic_id=topic_id, subtopic_ids=subtopic_ids, rationale="tagged right"
        )
    if response_model is DifficultyVerdict:
        return DifficultyVerdict(difficulty=difficulty, rationale="matches")
    if response_model is GeneratabilityVerdict:
        return GeneratabilityVerdict(should_have_generated=True, rationale="enough material")
    raise AssertionError(f"Unexpected response model: {response_model!r}")


class MetricJudgeClient:
    """Answers whichever verdict it is asked for, configurably.

    Defaults to the answer that passes every metric, so a test that cares about
    one metric only has to say what that one should say. Given a ``draft``, it
    also answers generation calls -- generation and judging happen in one
    ``GenerationService`` pass and share a client.
    """

    def __init__(
        self,
        *,
        topic_id: int = 1,
        subtopic_ids: list[int] | None = None,
        difficulty: Difficulty = Difficulty.EASY,
        issue_codes: list[RejectionReason] | None = None,
        custom_issue: str | None = None,
        should_have_generated: bool = True,
        draft: BaseModel | None = None,
        description: str = "fake/judge-model",
    ) -> None:
        # With a draft in hand, default to agreeing with what it claimed: a
        # test about generation should not have to restate the taxonomy twice to
        # avoid an incidental subtopic disagreement.
        self.topic_id = getattr(draft, "topic_id", None) or topic_id
        self.subtopic_ids = (
            subtopic_ids
            if subtopic_ids is not None
            else list(getattr(draft, "subtopic_ids", None) or [1])
        )
        self.difficulty = difficulty
        self.issue_codes = issue_codes or []
        self.custom_issue = custom_issue
        self.should_have_generated = should_have_generated
        self.draft = draft
        self._description = description
        self.calls = 0
        self.prompts: list[str] = []
        self.generation_calls: list[dict[str, Any]] = []

    @property
    def description(self) -> str:
        return self._description

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **_: Any
    ) -> BaseModel:
        self.calls += 1
        self.prompts.append(prompt)
        if self.draft is not None and isinstance(self.draft, response_model):
            self.generation_calls.append(
                {"system": system, "prompt": prompt, "model": response_model}
            )
            return self.draft
        if response_model is IssuesVerdict:
            return IssuesVerdict(
                issue_codes=self.issue_codes,
                custom_issue=self.custom_issue,
                rationale="issues rationale",
            )
        if response_model is SubtopicVerdict:
            return SubtopicVerdict(
                topic_id=self.topic_id,
                subtopic_ids=self.subtopic_ids,
                rationale="subtopic rationale",
            )
        if response_model is DifficultyVerdict:
            return DifficultyVerdict(difficulty=self.difficulty, rationale="difficulty rationale")
        if response_model is GeneratabilityVerdict:
            return GeneratabilityVerdict(
                should_have_generated=self.should_have_generated,
                rationale="generatability rationale",
            )
        raise AssertionError(f"Unexpected response model: {response_model!r}")


class SequencedDraftClient(MetricJudgeClient):
    """Returns a different generation draft per call, judging normally in between.

    For the claim-retry path (ADR-032): a run that misclassifies and then corrects
    itself needs the second call to answer differently from the first, which a
    single fixed ``draft`` cannot express. The last draft repeats once the sequence
    is exhausted, so a test can say "wrong twice, then right" without counting the
    judge's calls too.
    """

    def __init__(self, *, drafts: list[TaxonomyClaim], **kwargs: Any) -> None:
        if not drafts:
            raise AssertionError("SequencedDraftClient needs at least one draft.")
        super().__init__(draft=drafts[0], **kwargs)
        self.drafts = drafts
        self.draft_calls = 0

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        if isinstance(self.drafts[0], response_model):
            index = min(self.draft_calls, len(self.drafts) - 1)
            self.draft_calls += 1
            self.draft = self.drafts[index]
            # Keep the subtopic judge agreeing with whatever was last claimed, so a
            # retry test is not also a calibration test.
            self.topic_id = self.draft.topic_id
            self.subtopic_ids = list(self.draft.subtopic_ids)
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


class MalformedThenGoodClient(MetricJudgeClient):
    """Fails to return a readable draft N times, then answers normally.

    Reproduces the observed failure: the provider replies with the JSON *schema*
    of the draft instead of an instance, which Instructor surfaces as
    :class:`~app.errors.MalformedModelOutputError`.
    """

    def __init__(self, *, malformed_replies: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.malformed_replies = malformed_replies
        self.malformed_seen = 0

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        generating = self.draft is not None and isinstance(self.draft, response_model)
        if generating and self.malformed_seen < self.malformed_replies:
            self.malformed_seen += 1
            self.calls += 1
            self.prompts.append(prompt)
            raise MalformedModelOutputError(
                "The model did not return a usable structured answer.",
                detail=(
                    f"ValidationError: 6 validation errors for {response_model.__name__} "
                    "topic_id Field required [type=missing, input_value="
                    "{'description': '...', 'type': 'object'}]"
                ),
            )
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


class RaisingJudgeClient:
    """Raises ``error`` on every call, to exercise the retry ceiling."""

    def __init__(self, error: Exception, description: str = "fake/broken-judge") -> None:
        self.error = error
        self._description = description
        self.calls = 0

    @property
    def description(self) -> str:
        return self._description

    def complete_structured(self, **_: Any) -> BaseModel:
        self.calls += 1
        raise self.error


class FlakyJudgeClient(MetricJudgeClient):
    """Fails a fixed number of times per metric, then answers normally."""

    def __init__(self, *, failures_per_metric: int, error: Exception, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.failures_per_metric = failures_per_metric
        self.error = error
        self._failures: dict[str, int] = {}

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        seen = self._failures.get(response_model.__name__, 0)
        if seen < self.failures_per_metric:
            self._failures[response_model.__name__] = seen + 1
            self.calls += 1
            raise self.error
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )
