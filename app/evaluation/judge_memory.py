"""MemAlign memory for the judges: guidelines + nearest episodes, frozen per round.

ADR-064 decision 4-5, m11. The shipped prompt stays; active ``judge:<metric>`` guidelines
and the k nearest past cases are rendered onto it. A round freezes one snapshot after the
lesson run; later reviews do not change what that round's judges see. A candidate snapshot
is promoted only when held-out agreement does not drop and the known-bad pass rate does
not rise.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calibration.schema import PROFESSOR_OBJECTIONS
from app.domain.enums import JudgeMetricId, ReviewDecision
from app.domain.questions import Question
from app.evaluation.prompts import system_prompt_for
from app.memory import (
    SOURCE_AUDIT,
    SOURCE_BORDERLINE,
    SOURCE_REVIEW,
    MemoryEpisodeRepository,
    active_guidelines,
    distill_guidelines,
    judge_target,
    render_with_guidelines,
)
from app.persistence.models import (
    JudgeMemorySnapshotRow,
    MemoryEpisodeRow,
    ReviewOutcomeRow,
)
from app.subjects import SubjectProfile

#: Past cases shown to one judge.
MAX_JUDGE_EPISODES = 4

_MEMORY_METRICS: tuple[JudgeMetricId, ...] = (
    JudgeMetricId.ISSUES,
    JudgeMetricId.DIFFICULTY,
    JudgeMetricId.SUBTOPIC,
)

_CASE_SOURCES = frozenset({SOURCE_REVIEW, SOURCE_AUDIT, SOURCE_BORDERLINE})


@dataclass(frozen=True)
class SnapshotScore:
    """Held-out agreement and how often the judge passed a known-bad question."""

    agreement: float
    known_bad_pass_rate: float


SnapshotScorer = Callable[[JudgeMemorySnapshotRow], SnapshotScore]


#: Reasons that name one judge. A reject or edit citing none of them is generic quality
#: feedback, which belongs to the issues judge only.
_ATTRIBUTABLE = frozenset().union(*PROFESSOR_OBJECTIONS.values())


def _verdict(episode: MemoryEpisodeRow, metric: JudgeMetricId) -> dict:
    return (episode.judge_verdicts or {}).get(metric.value) or {}


def _judge_value(episode: MemoryEpisodeRow, metric: JudgeMetricId) -> object | None:
    """What the difficulty or subtopic judge said the value is; ``None`` if it did not say.

    A passing verdict without a proposal agreed with the question as reviewed.
    """
    verdict = _verdict(episode, metric)
    passed = verdict.get("passed")
    if metric is JudgeMetricId.DIFFICULTY:
        proposed = verdict.get("proposed_difficulty")
        if proposed is None and passed is True:
            proposed = episode.difficulty
        return None if proposed is None else str(proposed)
    proposed_ids = verdict.get("proposed_subtopic_ids") or []
    if not proposed_ids and passed is True:
        proposed_ids = episode.subtopic_ids or []
    return frozenset(proposed_ids) if proposed_ids else None


def _professor_value(episode: MemoryEpisodeRow, metric: JudgeMetricId) -> object:
    if metric is JudgeMetricId.DIFFICULTY:
        return str(episode.effective_difficulty)
    return frozenset(episode.effective_subtopic_ids)


def episode_teaches(episode: MemoryEpisodeRow, metric: JudgeMetricId) -> bool:
    """Whether this episode is evidence a judge's guidelines should learn from.

    Difficulty and subtopic: only when the professor's confirmed value differs from what
    the judge said, or the professor cited that judge's reason. Issues: an issue reason,
    a reject or edit with a comment and no attributable reason (generic quality feedback),
    or an approval the issues judge objected to. A review about something else never
    reaches a judge's distiller, whatever its comment says.
    """
    if episode.source not in _CASE_SOURCES:
        return False
    reasons = set(episode.reasons or [])
    if reasons & PROFESSOR_OBJECTIONS[metric]:
        return True
    if metric in (JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC):
        said = _judge_value(episode, metric)
        return said is not None and said != _professor_value(episode, metric)
    if episode.decision in (ReviewDecision.REJECT, ReviewDecision.EDIT):
        return bool(episode.comment) and not reasons & _ATTRIBUTABLE
    return (
        episode.decision is ReviewDecision.APPROVE
        and _verdict(episode, metric).get("passed") is False
    )


def episode_confirms(episode: MemoryEpisodeRow, metric: JudgeMetricId) -> bool:
    """Whether the judge matched the professor here: a past case it may see, not a lesson."""
    if episode.source not in _CASE_SOURCES or episode_teaches(episode, metric):
        return False
    if metric in (JudgeMetricId.DIFFICULTY, JudgeMetricId.SUBTOPIC):
        return _judge_value(episode, metric) is not None
    passed = _verdict(episode, metric).get("passed")
    if episode.decision is ReviewDecision.APPROVE:
        return passed is True
    return passed is False


def _professor_said(episode: MemoryEpisodeRow, metric: JudgeMetricId) -> str:
    """The professor's answer to this judge's question, not the overall verdict."""
    if metric is JudgeMetricId.DIFFICULTY:
        return f"difficulty {episode.effective_difficulty.value}"
    if metric is JudgeMetricId.SUBTOPIC:
        ids = ", ".join(str(i) for i in episode.effective_subtopic_ids) or "-"
        return f"subtopic ids {ids}"
    return episode.decision.value if episode.decision is not None else episode.source


def render_judge_cases(base: str, cases: Sequence[MemoryEpisodeRow], metric: JudgeMetricId) -> str:
    """Append nearest past cases: what the judge said and what the professor decided."""
    if not cases:
        return base
    lines = [base, "", "Past cases for this judge (what you said, what the professor decided):"]
    for episode in cases:
        verdict = _verdict(episode, metric)
        passed = verdict.get("passed")
        if verdict.get("rationale"):
            you = verdict["rationale"]
        elif passed is True:
            you = "passed"
        elif passed is False:
            you = "objected"
        else:
            you = "-"
        lines.append(f"- Question: {episode.text[:240]}")
        lines.append(f"  You said: {you}")
        lines.append(f"  Professor: {_professor_said(episode, metric)}")
    return "\n".join(lines)


def retrieve_judge_episodes(
    session: Session,
    *,
    metric: JudgeMetricId,
    subject: str,
    question: Question | None = None,
    limit: int = MAX_JUDGE_EPISODES,
    created_before: datetime | None = None,
) -> list[MemoryEpisodeRow]:
    """The k episodes this judge should see, newest or nearest the question first."""
    rows = [
        row
        for row in MemoryEpisodeRepository(session).of_source(SOURCE_REVIEW, subject=subject)
        + MemoryEpisodeRepository(session).of_source(SOURCE_AUDIT, subject=subject)
        + MemoryEpisodeRepository(session).of_source(SOURCE_BORDERLINE, subject=subject)
        if (episode_teaches(row, metric) or episode_confirms(row, metric))
        and _is_before(row.created_at, created_before)
    ]
    if question is not None and rows:
        query = question.prompt or ""
        rows = sorted(rows, key=lambda row: -_overlap(query, row.text))
    else:
        rows = sorted(rows, key=lambda row: row.id, reverse=True)
    return rows[:limit]


def compose_judge_system(
    session: Session,
    metric: JudgeMetricId,
    profile: SubjectProfile,
    *,
    question: Question | None = None,
    snapshot: JudgeMemorySnapshotRow | None = None,
    base: str | None = None,
    created_before: datetime | None = None,
) -> str:
    """Shipped (or hand-written) prompt + this judge's guidelines + nearest cases."""
    shipped = base if base is not None else system_prompt_for(metric, profile)
    if snapshot is not None:
        texts = list((snapshot.guidelines or {}).get(metric.value) or [])
        freeze = snapshot.created_at
    else:
        texts = [
            row.text
            for row in active_guidelines(
                session, target=judge_target(metric), subject=profile.personal_key
            )
        ]
        freeze = created_before
    rendered = render_with_guidelines(shipped, texts)
    cases = retrieve_judge_episodes(
        session,
        metric=metric,
        subject=profile.personal_key,
        question=question,
        created_before=freeze,
    )
    return render_judge_cases(rendered, cases, metric)


def capture_snapshot(session: Session, subject: str) -> JudgeMemorySnapshotRow:
    """Freeze the current active judge guidelines."""
    payload = {
        metric.value: [
            row.text
            for row in active_guidelines(session, target=judge_target(metric), subject=subject)
        ]
        for metric in _MEMORY_METRICS
    }
    row = JudgeMemorySnapshotRow(subject=subject, guidelines=payload, promoted=False)
    session.add(row)
    session.flush()
    return row


def latest_promoted(session: Session, subject: str) -> JudgeMemorySnapshotRow | None:
    return session.scalar(
        select(JudgeMemorySnapshotRow)
        .where(JudgeMemorySnapshotRow.subject == subject, JudgeMemorySnapshotRow.promoted.is_(True))
        .order_by(JudgeMemorySnapshotRow.id.desc())
    )


def promote_snapshot(
    session: Session,
    candidate: JudgeMemorySnapshotRow,
    *,
    scorer: SnapshotScorer | None = None,
) -> JudgeMemorySnapshotRow:
    """Promote ``candidate`` unless the scorer says it is worse than the incumbent."""
    previous = latest_promoted(session, candidate.subject)
    if previous is None or scorer is None:
        candidate.promoted = True
        session.flush()
        return candidate
    old = scorer(previous)
    new = scorer(candidate)
    if new.agreement >= old.agreement and new.known_bad_pass_rate <= old.known_bad_pass_rate:
        candidate.promoted = True
        session.flush()
        return candidate
    return previous


def apply_judge_lessons(
    session: Session,
    rows: list[ReviewOutcomeRow],
    profile: SubjectProfile,
    *,
    round_id: int | None = None,
    client=None,
    scorer: SnapshotScorer | None = None,
) -> JudgeMemorySnapshotRow | None:
    """Distil each judge that has new evidence, then freeze and maybe promote a snapshot."""
    review_ids = [row.review_id for row in rows if row.review_id]
    distilled = False
    for metric in _MEMORY_METRICS:
        relevant = [
            rid for rid in review_ids if _review_teaches(session, rid, metric, profile.personal_key)
        ]
        if not relevant:
            continue
        distill_guidelines(
            session,
            target=judge_target(metric),
            subject=profile.personal_key,
            question_type=None,
            review_ids=relevant,
            round_id=round_id,
            client=client,
        )
        distilled = True
    if not distilled:
        return latest_promoted(session, profile.personal_key)
    payload = {
        metric.value: [
            row.text
            for row in active_guidelines(
                session, target=judge_target(metric), subject=profile.personal_key
            )
        ]
        for metric in _MEMORY_METRICS
    }
    previous = latest_promoted(session, profile.personal_key)
    if previous is not None and (previous.guidelines or {}) == payload:
        return previous
    candidate = capture_snapshot(session, profile.personal_key)
    return promote_snapshot(session, candidate, scorer=scorer)


def _review_teaches(session: Session, review_id: int, metric: JudgeMetricId, subject: str) -> bool:
    episode = MemoryEpisodeRepository(session).get_for_review(review_id)
    return episode is not None and episode.subject == subject and episode_teaches(episode, metric)


def _is_before(stamp: datetime | None, cutoff: datetime | None) -> bool:
    """Whether ``stamp`` is strictly before ``cutoff``. Missing cutoff keeps the row."""
    if cutoff is None:
        return True
    if stamp is None:
        return False
    left = stamp.replace(tzinfo=None) if stamp.tzinfo else stamp
    right = cutoff.replace(tzinfo=None) if cutoff.tzinfo else cutoff
    return left < right


def _overlap(query: str, text: str) -> float:
    """Cheap token overlap so tests need no embedder; higher is nearer."""
    left = set(query.lower().split())
    right = set((text or "").lower().split())
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def memory_rubric_suffix(snapshot_id: int | None) -> str:
    """Appended to the panel name so trust keys on the snapshot."""
    return f"+mem{snapshot_id}" if snapshot_id is not None else ""
