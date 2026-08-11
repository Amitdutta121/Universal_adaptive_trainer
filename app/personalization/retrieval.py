"""Rank and select professor-reviewed examples for personalized generation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.enums import Difficulty, RejectionReason, ReviewDecision
from app.domain.feedback import REJECTION_REASON_LABELS
from app.generation.spec import QuestionSpec
from app.persistence.models import ProfessorReviewRow, QuestionRow, ReviewEmbeddingRow
from app.persistence.repositories import ProfessorReviewRepository, ReviewEmbeddingRepository
from app.personalization.embeddings import Embedder, cosine_similarity, example_content_hash

SUBTOPIC = 5.0
TOPIC = 2.0
TYPE = 2.0
DIFFICULTY_EXACT = 1.0
DIFFICULTY_ADJACENT = 0.5
DECISION_EDIT = 3.0
DECISION_APPROVE = 2.0
DECISION_REJECT = 1.0
RECENCY_MAX = 1.0
META_WEIGHT = 0.6
SEM_WEIGHT = 0.4
MIN_SCORE_FLOOR = 0.05

MAX_POSITIVE = 4
MAX_REJECTED = 2
REVIEW_LIMIT = 200

_DIFFICULTY_ORDER = (Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD)


@dataclass(frozen=True)
class RetrievedExample:
    review_id: int
    decision: ReviewDecision
    prompt: str
    reasons: list[RejectionReason]
    comment: str | None
    score: float
    question_id: int


@dataclass(frozen=True)
class RetrievalResult:
    approved_or_edited: list[RetrievedExample]
    rejected: list[RetrievedExample]


@dataclass
class _ScoredCandidate:
    review: ProfessorReviewRow
    question: QuestionRow
    meta_raw: float
    semantic: float
    final: float
    prompt: str
    reasons: list[RejectionReason]


def _difficulty_score(question_difficulty: Difficulty, spec_difficulty: Difficulty) -> float:
    if question_difficulty == spec_difficulty:
        return DIFFICULTY_EXACT
    try:
        q_idx = _DIFFICULTY_ORDER.index(question_difficulty)
        s_idx = _DIFFICULTY_ORDER.index(spec_difficulty)
    except ValueError:
        return 0.0
    if abs(q_idx - s_idx) == 1:
        return DIFFICULTY_ADJACENT
    return 0.0


def _decision_score(decision: ReviewDecision) -> float:
    if decision == ReviewDecision.EDIT:
        return DECISION_EDIT
    if decision == ReviewDecision.APPROVE:
        return DECISION_APPROVE
    return DECISION_REJECT


def _recency_score(rank: int, total: int) -> float:
    if total <= 1:
        return RECENCY_MAX
    return RECENCY_MAX * (1.0 - rank / (total - 1))


def _example_prompt(review: ProfessorReviewRow, question: QuestionRow) -> str:
    if review.decision == ReviewDecision.EDIT and review.edited_prompt:
        return review.edited_prompt
    return question.prompt


def _build_example_text(review: ProfessorReviewRow, question: QuestionRow) -> str:
    parts = [_example_prompt(review, question)]
    reasons = review.reasons
    if reasons:
        labels = [REJECTION_REASON_LABELS[reason] for reason in reasons]
        parts.append(" ".join(labels))
    if review.comment:
        parts.append(review.comment.strip())
    return "\n".join(part for part in parts if part)


def _build_query_text(
    *,
    topic_name: str,
    subtopic_names: list[str],
    spec: QuestionSpec,
    citation: str,
) -> str:
    return (
        f"{topic_name}\n{', '.join(subtopic_names)}\n"
        f"{spec.question_type.value}\n{spec.difficulty.value}\n{citation}"
    )


def _meta_raw_score(
    *,
    review: ProfessorReviewRow,
    question: QuestionRow,
    spec: QuestionSpec,
    topic_id: int,
    recency_rank: int,
    total_candidates: int,
) -> float:
    score = _decision_score(review.decision) + _recency_score(recency_rank, total_candidates)
    if question.subtopic_id is not None and question.subtopic_id in spec.subtopic_ids:
        score += SUBTOPIC
    elif question.topic_id == topic_id:
        score += TOPIC
    if question.question_type == spec.question_type:
        score += TYPE
    score += _difficulty_score(question.difficulty, spec.difficulty)
    return score


def _fill_ranked_pool(
    ranked: list[_ScoredCandidate],
    budget: int,
    *,
    floor: float = MIN_SCORE_FLOOR,
) -> list[_ScoredCandidate]:
    pool: list[_ScoredCandidate] = []
    for candidate in ranked:
        if candidate.final < floor:
            continue
        pool.append(candidate)
        if len(pool) >= budget:
            break
    return pool


def _ensure_embeddings(
    session: Session,
    *,
    reviews: list[ProfessorReviewRow],
    embedder: Embedder,
) -> dict[int, list[float]]:
    emb_repo = ReviewEmbeddingRepository(session)
    vectors: dict[int, list[float]] = {}
    pending_reviews: list[ProfessorReviewRow] = []
    pending_texts: list[str] = []

    for review in reviews:
        question = review.question
        text = _build_example_text(review, question)
        content_hash = example_content_hash(text)
        existing = emb_repo.get_for_review(review.id)
        if (
            existing is not None
            and existing.model_id == embedder.model_id
            and existing.content_hash == content_hash
        ):
            vectors[review.id] = existing.vector
            continue
        pending_reviews.append(review)
        pending_texts.append(text)

    if pending_texts:
        embedded = embedder.embed(pending_texts)
        for review, text, vector in zip(pending_reviews, pending_texts, embedded, strict=True):
            emb_repo.upsert(
                ReviewEmbeddingRow(
                    review_id=review.id,
                    model_id=embedder.model_id,
                    vector=vector,
                    content_hash=example_content_hash(text),
                )
            )
            vectors[review.id] = vector

    return vectors


def retrieve_examples(
    session: Session,
    *,
    spec: QuestionSpec,
    topic_id: int,
    topic_name: str,
    subtopic_names: list[str],
    citation: str,
    embedder: Embedder | None = None,
) -> RetrievalResult:
    reviews = ProfessorReviewRepository(session).list_with_questions(limit=REVIEW_LIMIT)
    if not reviews:
        return RetrievalResult(approved_or_edited=[], rejected=[])

    query_vector: list[float] | None = None
    review_vectors: dict[int, list[float]] = {}
    if embedder is not None:
        query_text = _build_query_text(
            topic_name=topic_name,
            subtopic_names=subtopic_names,
            spec=spec,
            citation=citation,
        )
        query_vector = embedder.embed([query_text])[0]
        review_vectors = _ensure_embeddings(session, reviews=reviews, embedder=embedder)

    total = len(reviews)
    meta_raws: list[float] = []
    candidates: list[_ScoredCandidate] = []

    for rank, review in enumerate(reviews):
        question = review.question
        reasons = review.reasons
        meta_raw = _meta_raw_score(
            review=review,
            question=question,
            spec=spec,
            topic_id=topic_id,
            recency_rank=rank,
            total_candidates=total,
        )
        meta_raws.append(meta_raw)
        semantic = 0.0
        if query_vector is not None:
            semantic = cosine_similarity(query_vector, review_vectors[review.id])
        candidates.append(
            _ScoredCandidate(
                review=review,
                question=question,
                meta_raw=meta_raw,
                semantic=semantic,
                final=0.0,
                prompt=_example_prompt(review, question),
                reasons=reasons,
            )
        )

    max_meta = max(meta_raws) if meta_raws else 1.0
    if max_meta <= 0.0:
        max_meta = 1.0

    for candidate in candidates:
        meta_norm = candidate.meta_raw / max_meta
        candidate.final = META_WEIGHT * meta_norm + SEM_WEIGHT * candidate.semantic

    positive: list[RetrievedExample] = []
    negative: list[RetrievedExample] = []

    for pool, decision_set, budget in (
        (positive, {ReviewDecision.APPROVE, ReviewDecision.EDIT}, MAX_POSITIVE),
        (negative, {ReviewDecision.REJECT}, MAX_REJECTED),
    ):
        ranked = sorted(
            (c for c in candidates if c.review.decision in decision_set),
            key=lambda c: c.final,
            reverse=True,
        )
        for candidate in _fill_ranked_pool(ranked, budget):
            pool.append(
                RetrievedExample(
                    review_id=candidate.review.id,
                    decision=candidate.review.decision,
                    prompt=candidate.prompt,
                    reasons=candidate.reasons,
                    comment=candidate.review.comment,
                    score=candidate.final,
                    question_id=candidate.question.id,
                )
            )

    return RetrievalResult(approved_or_edited=positive, rejected=negative)
