"""Professor-evidence trust and transactional one-in-ten generated-question audits.

These helpers flush, but never commit. Call the router in the same transaction as
question/evaluation persistence. Automatic approval never creates a review.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.enums import QuestionStatus, ReviewDecision
from app.persistence.models import (
    CurriculumVersionRow,
    CustomJudgeRow,
    JudgeTrustCounterRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    SubtopicRow,
)

#: The professor's own accept/reject, tracked like a judge so trust needs it too.
ACCEPTANCE = "acceptance"


@dataclass(frozen=True)
class MetricTrust:
    observations: int
    agreements: int
    agreement_rate: float
    trusted: bool
    audit_revoked: bool = False


@dataclass(frozen=True)
class TrustReport:
    trusted: bool
    eligible: bool
    metrics: dict[str, MetricTrust]
    scope_key: str


def _dict(value: Any) -> dict:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _rules(session: Session, question: QuestionRow) -> list[CustomJudgeRow]:
    return list(
        session.scalars(
            select(CustomJudgeRow)
            .where(
                CustomJudgeRow.curriculum_version_id == question.curriculum_version_id,
                CustomJudgeRow.enabled.is_(True),
            )
            .order_by(CustomJudgeRow.id)
        )
    )


def _rule_version(rule: CustomJudgeRow) -> str:
    # Include edit time: reverting to an earlier text still needs fresh evidence.
    edited = rule.updated_at.replace(tzinfo=None).isoformat() if rule.updated_at else None
    return _hash([rule.id, rule.rule_text, rule.kind, rule.pattern, edited])


def _snapshot(session: Session, question: QuestionRow, custom_results: Any) -> dict:
    evaluation = question.pedagogical_eval or {}
    if custom_results is None:
        latest = session.scalar(
            select(QuestionEvaluationRow)
            .where(
                QuestionEvaluationRow.question_id == question.id,
            )
            .order_by(QuestionEvaluationRow.created_at.desc(), QuestionEvaluationRow.id.desc())
        )
        custom_results = latest.custom_results if latest else []
    rules = _rules(session, question)
    return {
        "evaluation": evaluation,
        "custom_results": [_dict(result) for result in (custom_results or [])],
        "rule_versions": {str(rule.id): _rule_version(rule) for rule in rules},
        "difficulty": str(question.difficulty),
        "topic_id": question.topic_id,
        "subtopic_ids": list(question.subtopic_ids),
    }


def _metric_map(evaluation: dict) -> dict[str, dict]:
    return {str(item.get("metric")): item for item in evaluation.get("metrics", [])}


def _answered(metric: dict | None) -> bool:
    return bool(
        metric and metric.get("status") == "completed" and type(metric.get("passed")) is bool
    )


def _observation(
    session: Session, review: ProfessorReviewRow, snapshot: dict, name: str
) -> bool | None:
    metric = _metric_map(snapshot.get("evaluation", {})).get(name)
    if not _answered(metric):
        return None
    if name == "difficulty":
        if review.corrected_difficulty is None:
            return None
        proposed = metric.get("proposed_difficulty")
        if proposed is None and metric.get("passed") is True:
            proposed = snapshot.get("difficulty")
        return None if proposed is None else str(review.corrected_difficulty) == str(proposed)
    if not review.corrected_subtopic_ids:
        return None
    if snapshot.get("topic_id") is None:
        return None
    proposed = metric.get("proposed_subtopic_ids")
    topic = metric.get("proposed_topic_id")
    if not proposed and metric.get("passed") is True:
        proposed = snapshot.get("subtopic_ids")
        topic = snapshot.get("topic_id")
    if not proposed or topic is None:
        return None
    corrected = [
        session.get(SubtopicRow, identifier) for identifier in review.corrected_subtopic_ids
    ]
    if any(row is None for row in corrected):
        return None
    professor_topics = {row.topic_id for row in corrected}
    return set(review.corrected_subtopic_ids) == set(proposed) and professor_topics == {topic}


def _historical_snapshot(
    session: Session, question: QuestionRow, review: ProfessorReviewRow
) -> dict | None:
    if question.trust_snapshot:
        return question.trust_snapshot
    # Legacy evidence must have an immutable evaluation preceding the review;
    # never pair an old review with a later bulk re-judge or live question edits.
    history = session.scalar(
        select(QuestionEvaluationRow)
        .where(
            QuestionEvaluationRow.question_id == question.id,
            QuestionEvaluationRow.created_at <= review.created_at,
        )
        .order_by(QuestionEvaluationRow.created_at.desc(), QuestionEvaluationRow.id.desc())
    )
    if history is None:
        return None
    return {
        "evaluation": history.evaluation or {},
        "custom_results": history.custom_results or [],
        "rule_versions": {},
        "evaluated_at": history.created_at,
        "topic_id": (question.spec or {}).get("topic_id"),
        "difficulty": (question.spec or {}).get("difficulty"),
        "subtopic_ids": (question.spec or {}).get("subtopic_ids"),
    }


def judge_trust(
    session: Session, question_row: QuestionRow, custom_results: Any = None
) -> TrustReport:
    """Query trust for the current judge/rules and course/taxonomy/style scope.

    Null corrections are absent observations. Each metric uses its own most
    recent window of explicit observations. An audit disagreement blocks that
    metric immediately until a fresh minimum of distinct professor observations
    after that audit restores the window rate. Repeated edits do not add evidence.
    """
    session.flush()
    settings = get_settings()
    snapshot = _snapshot(session, question_row, custom_results)
    evaluation = snapshot["evaluation"]
    rules = _rules(session, question_row)
    version = session.get(CurriculumVersionRow, question_row.curriculum_version_id)
    scope_key = _hash(
        [
            version.course_id if version else None,
            question_row.curriculum_version_id,
            question_row.style_id,
            evaluation.get("judge_model"),
            evaluation.get("rubric_version"),
            snapshot["rule_versions"],
        ]
    )
    names = ["difficulty", "subtopic", ACCEPTANCE, *(f"custom:{rule.id}" for rule in rules)]
    observations: dict[str, list[tuple[bool, int]]] = {name: [] for name in names}
    seen: dict[str, set[int]] = {name: set() for name in names}
    failed_audit: dict[str, int] = dict.fromkeys(names, -1)
    # Ascending order selects the first explicit observation of each artifact.
    pairs = session.execute(
        select(ProfessorReviewRow, QuestionRow)
        .join(
            QuestionRow,
            QuestionRow.id == ProfessorReviewRow.question_id,
        )
        .where(
            QuestionRow.curriculum_version_id == question_row.curriculum_version_id,
            QuestionRow.style_id == question_row.style_id,
        )
        .order_by(ProfessorReviewRow.created_at, ProfessorReviewRow.id)
    )
    for event, (review, question) in enumerate(pairs):
        old = _historical_snapshot(session, question, review)
        if not old:
            continue
        old_eval = old.get("evaluation", {})
        if old_eval.get("judge_model") != evaluation.get("judge_model") or old_eval.get(
            "rubric_version"
        ) != evaluation.get("rubric_version"):
            continue
        if question.trust_provenance == "audit" and review.decision == ReviewDecision.REJECT:
            failed_audit = dict.fromkeys(names, event)
        for name in ("difficulty", "subtopic"):
            answer = _observation(session, review, old, name)
            if answer is False and question.trust_provenance == "audit":
                failed_audit[name] = event
            if answer is not None and question.id not in seen[name]:
                observations[name].append((answer, event))
                seen[name].add(question.id)
        if question.id not in seen[ACCEPTANCE]:
            observations[ACCEPTANCE].append((review.decision == ReviewDecision.APPROVE, event))
            seen[ACCEPTANCE].add(question.id)
        results = {item.get("judge_id"): item for item in old.get("custom_results", [])}
        for rule in rules:
            result = results.get(rule.id)
            if not result or type(result.get("passed")) is not bool:
                continue
            if result.get("rule_text") != rule.rule_text or result.get("kind") != str(rule.kind):
                continue
            stored_version = old.get("rule_versions", {}).get(str(rule.id))
            if stored_version is not None:
                if stored_version != _rule_version(rule):
                    continue
            else:
                # Pattern identity was not stored in legacy CustomJudgeResult.
                # Exclude it rather than accidentally reuse a different regex.
                if rule.pattern is not None:
                    continue
                evaluated = old.get("evaluated_at")
                if rule.updated_at and (
                    not evaluated
                    or evaluated.replace(tzinfo=None) < rule.updated_at.replace(tzinfo=None)
                ):
                    continue
            # Only an unedited explicit acceptance of a passing rule agrees.
            agreement = review.decision == ReviewDecision.APPROVE and result["passed"] is True
            name = f"custom:{rule.id}"
            if not agreement and question.trust_provenance == "audit":
                failed_audit[name] = event
            if question.id not in seen[name]:
                observations[name].append((agreement, event))
                seen[name].add(question.id)
    metrics: dict[str, MetricTrust] = {}
    window = max(settings.judge_trust_window, settings.judge_trust_min_observations)
    for name, values in observations.items():
        recent = list(reversed(values))[:window]
        count, agrees = len(recent), sum(value[0] for value in recent)
        rate = agrees / count if count else 0.0
        minimum = (
            settings.judge_trust_min_acceptance
            if name == ACCEPTANCE
            else settings.judge_trust_min_agreement
        )
        revoked = (
            failed_audit[name] >= 0
            and sum(event > failed_audit[name] for _, event in values)
            < settings.judge_trust_min_observations
        )
        metrics[name] = MetricTrust(
            count,
            agrees,
            rate,
            count >= settings.judge_trust_min_observations
            and rate >= minimum
            and not revoked,
            revoked,
        )
    current = _metric_map(evaluation)
    results = {item.get("judge_id"): item for item in snapshot["custom_results"]}
    panel = set(settings.judge_metrics_enabled) | {"difficulty", "subtopic"}
    eligible = bool(
        version
        and question_row.style_id
        and evaluation.get("judge_model")
        and evaluation.get("rubric_version")
        and evaluation.get("status") == "completed"
    )
    eligible = eligible and all(
        _answered(current.get(name)) and current[name]["passed"] is True for name in panel
    )
    # Extra shipped judges have no explicit professor truth labels in this API.
    # Running one requires manual review until its own trust evidence exists.
    eligible = eligible and panel <= {"difficulty", "subtopic"}
    eligible = eligible and all(
        result.get("passed") is True
        and result.get("rule_text") == rule.rule_text
        and result.get("kind") == str(rule.kind)
        for rule in rules
        for result in [results.get(rule.id, {})]
    )
    return TrustReport(
        all(metric.trusted for metric in metrics.values()), bool(eligible), metrics, scope_key
    )


def route_generated_question(
    session: Session,
    question_row: QuestionRow,
    custom_results: Any = None,
    *,
    hold_for_review: bool = False,
) -> str:
    """Persist ``auto_approved``, ``audit`` or ``pending``; every tenth eligible
    trusted question is an audit. Repeated calls return the original decision.

    ``hold_for_review`` routes to ``pending`` however trusted the scope, without
    counting toward the audit sequence: the caller knows something the judges do
    not (a round question kept on its last attempt as a duplicate, ADR-063 point 6).

    The conditional question claim and atomic counter increment share the
    caller's transaction, so rollback restores both. SQLite and PostgreSQL use
    ON CONFLICT RETURNING. Unsupported databases fail rather than skip auditing.
    """
    session.flush()
    claim = session.execute(
        update(QuestionRow)
        .where(
            QuestionRow.id == question_row.id,
            QuestionRow.trust_provenance.is_(None),
        )
        .values(trust_provenance="routing")
        .execution_options(synchronize_session=False)
    )
    if not claim.rowcount:
        session.refresh(question_row)
        return question_row.trust_provenance or "pending"
    report = judge_trust(session, question_row, custom_results)
    snapshot = _snapshot(session, question_row, custom_results)
    provenance, sequence = "pending", None
    if (
        not hold_for_review
        and report.trusted
        and report.eligible
        and question_row.status == QuestionStatus.VALIDATION_PASSED
    ):
        dialect = session.get_bind().dialect.name
        if dialect in {"sqlite", "postgresql"}:
            if dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                from sqlalchemy.dialects.postgresql import insert
            counter = insert(JudgeTrustCounterRow).values(
                scope_key=report.scope_key, eligible_count=1
            )
            sequence = session.scalar(
                counter.on_conflict_do_update(
                    index_elements=[JudgeTrustCounterRow.scope_key],
                    set_={"eligible_count": JudgeTrustCounterRow.eligible_count + 1},
                ).returning(JudgeTrustCounterRow.eligible_count)
            )
        else:
            raise NotImplementedError("Trust audit sequencing requires SQLite or PostgreSQL")
        provenance = "audit" if sequence % 10 == 0 else "auto_approved"
        if provenance == "auto_approved":
            question_row.status = QuestionStatus.APPROVED
    question_row.trust_provenance = provenance
    question_row.trust_scope_key = report.scope_key
    question_row.trust_sequence = sequence
    question_row.trust_snapshot = snapshot
    session.flush()
    return provenance
