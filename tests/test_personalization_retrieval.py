"""Example retrieval for personalized question generation."""

from __future__ import annotations

from dataclasses import dataclass

import book_documents as docs
import pytest
from sqlalchemy.orm import Session

from app.curriculum import TaxonomyImportService
from app.domain.enums import (
    Difficulty,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.feedback import submit_review
from app.generation.spec import QuestionSpec
from app.ingestion import BookImportService
from app.persistence.models import QuestionRow
from app.persistence.repositories import QuestionRepository, ReviewEmbeddingRepository
from app.personalization.embeddings import FakeEmbedder
from app.personalization.retrieval import (
    MAX_POSITIVE,
    MIN_SCORE_FLOOR,
    _fill_ranked_pool,
    _ScoredCandidate,
    retrieve_examples,
)


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder(dim=8)


@dataclass(frozen=True)
class SeededReviews:
    version_id: int
    topic_id: int
    subtopic_a_id: int
    subtopic_b_id: int
    section_id: int
    other_chapter_section_id: int
    same_section_review_id: int
    other_section_review_id: int
    edit_review_id: int
    approve_review_id: int
    reject_review_id: int


def _question(session: Session, **overrides: object) -> QuestionRow:
    values = {
        "prompt": "Write a loop.",
        "original_prompt": "Write a loop.",
        "reference_solution": "pass",
        "original_reference_solution": "pass",
        "tests": "assert True",
        "original_tests": "assert True",
        "generator_name": "base-gen",
        "generator_version": "1",
        "status": QuestionStatus.VALIDATION_PASSED,
    }
    values.update(overrides)
    row = QuestionRepository(session).add(QuestionRow(**values))
    session.commit()
    assert row.id is not None
    return row


def _seed_reviews(session: Session, settings) -> SeededReviews:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python())
    )
    taxonomy = (
        b'{"schema_version":"1","label":"T","topics":['
        b'{"name":"Strings","subtopics":['
        b'{"name":"Immutability"},{"name":"Methods"}'
        b"]}]}"
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=taxonomy
    )
    session.commit()
    topic = version.topics[0]
    sub_a = topic.subtopics[0]
    sub_b = topic.subtopics[1]
    section_id = book.chapters[0].sections[0].id
    other_chapter_section_id = book.chapters[1].sections[0].id

    base = {
        "curriculum_version_id": version.id,
        "topic_id": topic.id,
        "question_type": QuestionType.DEBUGGING,
        "difficulty": Difficulty.MEDIUM,
    }

    q_same = _question(
        session,
        **base,
        subtopic_ids=[sub_a.id],
        spec={"source_section_ids": [section_id]},
        prompt="Immutability debugging prompt about strings.",
    )
    review_same = submit_review(
        session,
        question_id=q_same.id,
        decision=ReviewDecision.APPROVE,
        comment="Good immutability example.",
    )

    q_other = _question(
        session,
        **base,
        subtopic_ids=[sub_b.id],
        spec={"source_section_ids": [other_chapter_section_id]},
        prompt="Methods debugging prompt about string methods.",
    )
    review_other = submit_review(
        session,
        question_id=q_other.id,
        decision=ReviewDecision.APPROVE,
        comment="Good methods example.",
    )

    q_edit = _question(
        session,
        **base,
        subtopic_ids=[sub_a.id],
        spec={"source_section_ids": [section_id]},
        prompt="Original edit prompt.",
    )
    review_edit = submit_review(
        session,
        question_id=q_edit.id,
        decision=ReviewDecision.EDIT,
        prompt="Edited immutability prompt.",
        reference_solution="pass",
        tests="assert True",
        reasons=[RejectionReason.POOR_WORDING],
        comment="Tighten wording.",
    )

    q_approve = _question(
        session,
        **base,
        subtopic_ids=[sub_a.id],
        spec={"source_section_ids": [section_id]},
        prompt="Plain approve prompt.",
    )
    review_approve = submit_review(
        session,
        question_id=q_approve.id,
        decision=ReviewDecision.APPROVE,
        comment="Fine as-is.",
    )

    q_reject = _question(
        session,
        **base,
        subtopic_ids=[sub_a.id],
        spec={"source_section_ids": [section_id]},
        prompt="Reject this prompt.",
    )
    review_reject = submit_review(
        session,
        question_id=q_reject.id,
        decision=ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        comment="Too simple.",
    )
    session.commit()

    assert review_same.id is not None
    assert review_other.id is not None
    assert review_edit.id is not None
    assert review_approve.id is not None
    assert review_reject.id is not None

    return SeededReviews(
        version_id=version.id,
        topic_id=topic.id,
        subtopic_a_id=sub_a.id,
        subtopic_b_id=sub_b.id,
        section_id=section_id,
        other_chapter_section_id=other_chapter_section_id,
        same_section_review_id=review_same.id,
        other_section_review_id=review_other.id,
        edit_review_id=review_edit.id,
        approve_review_id=review_approve.id,
        reject_review_id=review_reject.id,
    )


def _spec(seed: SeededReviews) -> QuestionSpec:
    return QuestionSpec(
        curriculum_version_id=seed.version_id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[seed.section_id],
    )


def _retrieve(
    session: Session,
    seed: SeededReviews,
    *,
    embedder: FakeEmbedder | None,
) -> object:
    return retrieve_examples(
        session,
        spec=_spec(seed),
        section_id=seed.section_id,
        section_text="Strings are immutable in Python.",
        citation="Book ch.1 sec.1",
        embedder=embedder,
    )


def test_retrieval_prefers_the_same_source_section(
    session: Session, settings, fake_embedder: FakeEmbedder
) -> None:
    """The generator has not chosen a subtopic yet, so proximity is the key."""
    seed = _seed_reviews(session, settings)
    result = _retrieve(session, seed, embedder=fake_embedder)
    positive_ids = [ex.review_id for ex in result.approved_or_edited]
    assert positive_ids.index(seed.same_section_review_id) < positive_ids.index(
        seed.other_section_review_id
    )


def test_retrieval_prefers_edit_over_approve(
    session: Session, settings, fake_embedder: FakeEmbedder
) -> None:
    seed = _seed_reviews(session, settings)
    result = _retrieve(session, seed, embedder=None)
    positive_ids = [ex.review_id for ex in result.approved_or_edited]
    assert positive_ids.index(seed.edit_review_id) < positive_ids.index(seed.approve_review_id)


def test_retrieval_reject_pool_ordered_by_metadata(
    session: Session, settings, fake_embedder: FakeEmbedder
) -> None:
    seed = _seed_reviews(session, settings)
    result = _retrieve(session, seed, embedder=None)
    assert len(result.rejected) == 1
    assert result.rejected[0].review_id == seed.reject_review_id
    assert result.rejected[0].decision == ReviewDecision.REJECT


def test_combined_score_uses_fake_embeddings(
    session: Session, settings, fake_embedder: FakeEmbedder
) -> None:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    taxonomy = (
        b'{"schema_version":"1","label":"T","topics":['
        b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=taxonomy
    )
    session.commit()
    topic = version.topics[0]
    sub = topic.subtopics[0]
    section_id = book.chapters[0].sections[0].id
    spec = QuestionSpec(
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )
    similar_prompt = "Immutability debugging prompt about strings."
    base = {
        "curriculum_version_id": version.id,
        "topic_id": topic.id,
        "subtopic_ids": [sub.id],
        "spec": {"source_section_ids": [section_id]},
        "question_type": QuestionType.DEBUGGING,
        "difficulty": Difficulty.MEDIUM,
    }
    q_similar = _question(session, **base, prompt=similar_prompt)
    review_similar = submit_review(
        session,
        question_id=q_similar.id,
        decision=ReviewDecision.APPROVE,
        comment="Semantically close.",
    )
    q_far = _question(session, **base, prompt="Totally unrelated quantum physics question.")
    review_far = submit_review(
        session,
        question_id=q_far.id,
        decision=ReviewDecision.APPROVE,
        comment="Unrelated.",
    )
    session.commit()
    assert review_similar.id is not None
    assert review_far.id is not None

    result = retrieve_examples(
        session,
        spec=spec,
        section_id=section_id,
        section_text="Immutability debugging prompt about strings.",
        citation="Book ch.1 sec.1",
        embedder=fake_embedder,
    )
    positive_ids = [ex.review_id for ex in result.approved_or_edited]
    assert positive_ids.index(review_similar.id) < positive_ids.index(review_far.id)

    emb_repo = ReviewEmbeddingRepository(session)
    similar_row = emb_repo.get_for_review(review_similar.id)
    far_row = emb_repo.get_for_review(review_far.id)
    assert similar_row is not None
    assert far_row is not None
    assert similar_row.model_id == fake_embedder.model_id


def test_retrieval_empty_history(session: Session, fake_embedder: FakeEmbedder) -> None:
    spec = QuestionSpec(
        curriculum_version_id=1,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[1],
    )
    result = retrieve_examples(
        session,
        spec=spec,
        section_id=1,
        section_text="Strings are immutable in Python.",
        citation="Book ch.1 sec.1",
        embedder=fake_embedder,
    )
    assert result.approved_or_edited == []
    assert result.rejected == []


def _seed_single_approve(session: Session, settings) -> tuple[SeededReviews, QuestionSpec]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    taxonomy = (
        b'{"schema_version":"1","label":"T","topics":['
        b'{"name":"Strings","subtopics":[{"name":"Immutability"}]}]}'
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="tax.json", data=taxonomy
    )
    session.commit()
    topic = version.topics[0]
    sub = topic.subtopics[0]
    section_id = book.chapters[0].sections[0].id
    q = _question(
        session,
        curriculum_version_id=version.id,
        topic_id=topic.id,
        subtopic_ids=[sub.id],
        spec={"source_section_ids": [section_id]},
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        prompt="Only one positive.",
    )
    submit_review(session, question_id=q.id, decision=ReviewDecision.APPROVE)
    session.commit()
    seed = SeededReviews(
        version_id=version.id,
        topic_id=topic.id,
        subtopic_a_id=sub.id,
        subtopic_b_id=sub.id,
        section_id=section_id,
        other_chapter_section_id=section_id,
        same_section_review_id=0,
        other_section_review_id=0,
        edit_review_id=0,
        approve_review_id=0,
        reject_review_id=0,
    )
    spec = QuestionSpec(
        curriculum_version_id=version.id,
        question_type=QuestionType.DEBUGGING,
        difficulty=Difficulty.MEDIUM,
        source_section_ids=[section_id],
    )
    return seed, spec


def test_partial_history_shrinks_budget(
    session: Session, settings, fake_embedder: FakeEmbedder
) -> None:
    seed, spec = _seed_single_approve(session, settings)
    result = retrieve_examples(
        session,
        spec=spec,
        section_id=seed.section_id,
        section_text="Strings are immutable in Python.",
        citation="Book ch.1 sec.1",
        embedder=fake_embedder,
    )
    assert len(result.approved_or_edited) == 1
    assert result.rejected == []


def test_never_exceed_caps(session: Session, settings, fake_embedder: FakeEmbedder) -> None:
    seed = _seed_reviews(session, settings)
    base = {
        "curriculum_version_id": seed.version_id,
        "topic_id": seed.topic_id,
        "subtopic_ids": [seed.subtopic_a_id],
        "spec": {"source_section_ids": [seed.section_id]},
        "question_type": QuestionType.DEBUGGING,
        "difficulty": Difficulty.MEDIUM,
    }
    for i in range(10):
        q = _question(session, **base, prompt=f"Positive overflow {i}.")
        submit_review(session, question_id=q.id, decision=ReviewDecision.APPROVE)
    for i in range(5):
        q = _question(session, **base, prompt=f"Negative overflow {i}.")
        submit_review(
            session,
            question_id=q.id,
            decision=ReviewDecision.REJECT,
            reasons=[RejectionReason.OTHER],
        )
    session.commit()

    result = _retrieve(session, seed, embedder=fake_embedder)
    assert len(result.approved_or_edited) <= 4
    assert len(result.rejected) <= 2


def test_fill_ranked_pool_backfills_after_floor_skips() -> None:
    """Slice-first would stop after budget slots even when later candidates pass the floor."""

    def _candidate(final: float) -> _ScoredCandidate:
        return _ScoredCandidate(
            review=object(),  # type: ignore[arg-type]
            question=object(),  # type: ignore[arg-type]
            meta_raw=0.0,
            semantic=0.0,
            final=final,
            prompt="",
            reasons=[],
        )

    # Deliberately unsorted: early slice holds sub-floor scores; later entries backfill.
    ranked = [
        _candidate(0.10),
        _candidate(0.03),
        _candidate(0.03),
        _candidate(0.03),
        _candidate(0.08),
        _candidate(0.07),
        _candidate(0.06),
    ]
    budget = 4
    floor = MIN_SCORE_FLOOR

    slice_first_count = sum(1 for candidate in ranked[:budget] if candidate.final >= floor)
    assert slice_first_count == 1

    selected = _fill_ranked_pool(ranked, budget, floor=floor)
    assert len(selected) == budget
    assert [candidate.final for candidate in selected] == [0.10, 0.08, 0.07, 0.06]
    assert all(candidate.final >= floor for candidate in selected)
    assert len(selected) <= MAX_POSITIVE


def test_retrieved_example_fields(session: Session, settings, fake_embedder: FakeEmbedder) -> None:
    seed = _seed_reviews(session, settings)
    result = _retrieve(session, seed, embedder=fake_embedder)
    edit = next(ex for ex in result.approved_or_edited if ex.review_id == seed.edit_review_id)
    assert edit.prompt == "Edited immutability prompt."
    assert edit.decision == ReviewDecision.EDIT
    assert RejectionReason.POOR_WORDING in edit.reasons
    assert edit.comment == "Tighten wording."
    assert edit.score >= 0.05
