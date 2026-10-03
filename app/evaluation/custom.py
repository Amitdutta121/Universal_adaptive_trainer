"""Custom rule judges: professor-written rules every generated question must pass.

Phase 0 contract (docs/QUESTION_SETUP_PLAN.md, agent C): the result model is final; the
runner is a stub. The round generator (agent B) calls :func:`run_custom_judges` inside its
retry loop, so a failing rule triggers a regeneration with ``reason`` as the correction.

Rules are not :class:`~app.domain.enums.JudgeMetricId` metrics: they are per-taxonomy data
(``CustomJudgeRow``) and their results are stored on ``QuestionEvaluationRow.custom_results``
as ``[CustomJudgeResult.model_dump(mode="json"), ...]``.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from app.domain.enums import CustomJudgeKind
from app.domain.questions import Question
from app.llm import StructuredLLMClient
from app.persistence.models import CustomJudgeRow


class CustomRule(BaseModel):
    """One enabled rule, detached from its row so the runner needs no session."""

    model_config = ConfigDict(frozen=True)

    id: int
    rule_text: str
    kind: CustomJudgeKind
    #: The regex a ``PATTERN`` rule checks; ``None`` for ``LLM`` rules.
    pattern: str | None = None

    @classmethod
    def from_row(cls, row: CustomJudgeRow) -> CustomRule:
        return cls(id=row.id, rule_text=row.rule_text, kind=row.kind, pattern=row.pattern)


class CustomJudgeResult(BaseModel):
    """What one rule said about one question."""

    #: ``CustomJudgeRow.id`` of the rule.
    judge_id: int
    #: The rule text at the time it was judged, so a later edit does not rewrite history.
    rule_text: str
    kind: CustomJudgeKind
    #: ``True`` passes, ``False`` fails, ``None`` means the judge could not answer (model
    #: error, unreadable pattern). ``None`` is an absent measurement, not a failure: it never
    #: triggers a regeneration.
    passed: bool | None
    #: Why it failed, phrased so it can be fed back to the generator as a correction.
    #: ``None`` when it passed.
    reason: str | None = None


def run_custom_judges(
    question: Question,
    rules: Sequence[CustomRule],
    *,
    client: StructuredLLMClient | None = None,
) -> list[CustomJudgeResult]:
    """Judge one question against every rule, returning one result per rule, in rule order.

    ``PATTERN`` rules match ``pattern`` (a regex) against the question's code (prompt code,
    reference solution); no model call. ``LLM`` rules make one yes/no structured call each via
    ``client`` (default: the judge client at ``judge_temperature``). Never raises for a single
    rule's failure -- that rule's result has ``passed=None``. An empty ``rules`` returns ``[]``
    without touching the client. Persists nothing; the caller stores the results.
    """
    raise NotImplementedError("app.evaluation.custom.run_custom_judges is a Phase 0 stub")
