"""Episodic memory (ADR-063 point 3, m4): one episode per review, read by round retrieval."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from types import SimpleNamespace

import pytest
from alembic import command
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.domain.enums import (
    CurriculumStatus,
    Difficulty,
    QuestionStatus,
    QuestionType,
    RejectionReason,
    ReviewDecision,
)
from app.feedback import delete_review, route_review_outcome, submit_review
from app.generation import rounds as rounds_module
from app.generation.prompts import RoundExamples
from app.persistence.database import _alembic_config, init_db
from app.persistence.models import (
    CourseRow,
    CurriculumVersionRow,
    MemoryEpisodeRow,
    ProfessorReviewRow,
    QuestionRow,
    ReviewOutcomeRow,
    SubtopicRow,
    TopicRow,
)

MCQ = QuestionType.MULTIPLE_CHOICE
OWNER = uuid.UUID("12345678-1234-5678-1234-567812345678")

#: A completed evaluation in the stored blob shape: the difficulty judge failed it.
EVALUATION = {
    "status": "completed",
    "gate": "needs_review",
    "rubric_version": "rubric-test",
    "metrics": [
        {"metric": "issues", "status": "completed", "passed": True, "rationale": "Clean."},
        {
            "metric": "difficulty",
            "status": "completed",
            "passed": False,
            "rationale": "Recall only.",
            "proposed_difficulty": "easy",
        },
        {
            "metric": "subtopic",
            "status": "completed",
            "passed": True,
            "rationale": "On target.",
            "proposed_subtopic_ids": [],
        },
        {"metric": "generatability", "status": "completed", "passed": True, "rationale": "Ok."},
    ],
}


class MarkerEmbedder:
    """Counts marker words; the target query (subtopic "While loops") holds only "while"."""

    model = "marker-test-v1"
    VOCAB = ("alpha", "beta", "gamma", "while")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) for word in self.VOCAB] for t in texts]


def _course(session: Session, name: str, subject: str = "intro_python") -> SimpleNamespace:
    course = CourseRow(name=name, subject=subject, owner_id=OWNER, question_types=["coding"])
    session.add(course)
    session.flush()
    version = CurriculumVersionRow(
        course_id=course.id, label=f"{name} v1", status=CurriculumStatus.APPROVED
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
    session.add(topic)
    session.flush()
    while_loops = SubtopicRow(topic_id=topic.id, name="While loops", position=0)
    for_loops = SubtopicRow(topic_id=topic.id, name="For loops", position=1)
    session.add_all([while_loops, for_loops])
    session.commit()
    return SimpleNamespace(
        course=course, version=version, while_loops=while_loops, for_loops=for_loops
    )


def _question(
    session: Session,
    env: SimpleNamespace,
    prompt: str,
    *,
    subtopic: SubtopicRow | None = None,
    difficulty: Difficulty = Difficulty.MEDIUM,
    question_type: QuestionType = MCQ,
    status: QuestionStatus = QuestionStatus.GENERATED,
    content: dict | None = None,
) -> QuestionRow:
    subtopic = subtopic or env.while_loops
    row = QuestionRow(
        curriculum_version_id=env.version.id,
        topic_id=subtopic.topic_id,
        subtopic_ids=[subtopic.id],
        difficulty=difficulty,
        status=status,
        prompt=prompt,
        reference_solution="",
        tests="",
        question_type=question_type,
        content=content,
        pedagogical_eval=EVALUATION,
    )
    session.add(row)
    session.commit()
    return row


def _review(
    session: Session, row: QuestionRow, decision: ReviewDecision, **kwargs
) -> ProfessorReviewRow:
    review = submit_review(session, question_id=row.id, decision=decision, **kwargs)
    route_review_outcome(session, review)
    session.commit()
    return review


def _episodes(session: Session) -> list[MemoryEpisodeRow]:
    return list(session.scalars(select(MemoryEpisodeRow).order_by(MemoryEpisodeRow.id)))


def _examples(session: Session, env: SimpleNamespace, embedder: object = None) -> RoundExamples:
    return rounds_module.accepted_examples(
        session,
        env.version.id,
        (env.while_loops.id, Difficulty.MEDIUM),
        MCQ,
        embedder=embedder,  # type: ignore[arg-type]
    )


def _texts(items: Sequence) -> list[str]:
    return [item.text for item in items]


@pytest.fixture
def env(session: Session) -> SimpleNamespace:
    return _course(session, "Python A")


# ------------------------------------------------------------------ write path


def test_every_review_writes_one_episode_with_the_judges_verdicts(
    session: Session, env: SimpleNamespace
) -> None:
    code = {"code": "while n:\n    n -= 1", "options": ["0", "1"]}
    approved = _question(session, env, "What is n after the loop?", content=code)
    rejected = _question(session, env, "What is a loop?")

    first = _review(
        session,
        approved,
        ReviewDecision.APPROVE,
        comment="  Good use of code.  ",
        corrected_difficulty=Difficulty.HARD,
        corrected_subtopic_ids=[env.for_loops.id],
    )
    second = _review(
        session,
        rejected,
        ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        comment="Definition only.",
    )

    episode, rejected_episode = _episodes(session)
    assert [episode.review_id, rejected_episode.review_id] == [first.id, second.id]
    assert episode.source == "review"
    assert episode.subject == f"intro_python@{OWNER.hex}"
    assert (episode.question_id, episode.question_type) == (approved.id, MCQ)
    # Frozen as reviewed: prompt + code + options, and the classification before correction.
    assert episode.text == "What is n after the loop?\nwhile n:\n    n -= 1\n0\n1"
    assert episode.original_text is None
    assert (episode.difficulty, episode.subtopic_ids) == (Difficulty.MEDIUM, [env.while_loops.id])
    assert episode.topic_id == env.while_loops.topic_id
    assert (episode.corrected_difficulty, episode.corrected_subtopic_ids) == (
        Difficulty.HARD,
        [env.for_loops.id],
    )
    assert episode.effective_difficulty is Difficulty.HARD
    assert episode.effective_subtopic_ids == [env.for_loops.id]
    assert (episode.decision, episode.comment) == (ReviewDecision.APPROVE, "Good use of code.")
    assert episode.rubric_version == "rubric-test"
    assert set(episode.judge_verdicts) == {"issues", "difficulty", "subtopic", "generatability"}
    assert episode.judge_verdicts["difficulty"]["passed"] is False
    assert episode.judge_verdicts["difficulty"]["rationale"] == "Recall only."
    assert episode.judge_verdicts["difficulty"]["proposed_difficulty"] == "easy"
    assert (rejected_episode.decision, rejected_episode.reasons) == (
        ReviewDecision.REJECT,
        [RejectionReason.TOO_EASY],
    )
    assert rejected_episode.comment == "Definition only."


def test_a_second_review_of_the_same_question_is_a_second_episode(
    session: Session, env: SimpleNamespace
) -> None:
    row = _question(session, env, "What does while do?")
    _review(session, row, ReviewDecision.APPROVE)
    _review(session, row, ReviewDecision.REJECT, reasons=[RejectionReason.AMBIGUOUS])

    assert session.scalar(select(func.count()).select_from(ProfessorReviewRow)) == 2
    assert [episode.decision for episode in _episodes(session)] == [
        ReviewDecision.APPROVE,
        ReviewDecision.REJECT,
    ]


def test_an_edit_stores_the_professors_version_and_keeps_the_generated_one(
    session: Session, env: SimpleNamespace
) -> None:
    row = _question(session, env, "Generated: what does while do?", content={"code": "while x:"})

    _review(
        session,
        row,
        ReviewDecision.EDIT,
        prompt="Professor: what does this loop print?",
        reference_solution="",
        tests="",
        comment="Ask about output.",
    )

    (episode,) = _episodes(session)
    assert episode.decision is ReviewDecision.EDIT
    assert episode.text == "Professor: what does this loop print?\nwhile x:"
    assert episode.original_text == "Generated: what does while do?\nwhile x:"


def test_saving_a_review_makes_no_embedding_call(
    session: Session, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.retrieval.duplicates as duplicates

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("no embedding at save time")

    monkeypatch.setattr(duplicates.QuestionEmbeddingStore, "embed_with", refuse)
    _review(session, _question(session, env, "Q?"), ReviewDecision.APPROVE)
    assert len(_episodes(session)) == 1


# ------------------------------------------------------------------ retrieval


def test_retrieval_shows_approved_examples_with_comment_and_one_rejected_with_reason(
    session: Session, env: SimpleNamespace
) -> None:
    _review(
        session,
        _question(session, env, "Choice while alpha"),
        ReviewDecision.APPROVE,
        comment="Exactly the level I want.",
    )
    edited = _question(session, env, "Generated beta")
    _review(
        session,
        edited,
        ReviewDecision.EDIT,
        prompt="Edited while beta",
        reference_solution="",
        tests="",
    )
    _review(
        session,
        _question(session, env, "Rejected gamma"),
        ReviewDecision.REJECT,
        reasons=[RejectionReason.POOR_DISTRACTORS],
    )
    _review(
        session,
        _question(session, env, "Rejected while while"),
        ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        comment="Asks for a definition.",
    )
    # Rejected with neither reason nor comment: nothing to say why, never shown.
    _review(session, _question(session, env, "Rejected while while while"), ReviewDecision.REJECT)

    found = _examples(session, env, MarkerEmbedder())

    assert _texts(found.accepted) == ["Edited while beta", "Choice while alpha"]
    assert [example.comment for example in found.accepted] == [None, "Exactly the level I want."]
    assert found.rejected is not None
    assert found.rejected.text == "Rejected while while"  # the nearest with a reason
    assert found.rejected.because == "Too easy; Asks for a definition."


def test_retrieval_without_an_embedder_takes_the_newest_rejected(
    session: Session, env: SimpleNamespace
) -> None:
    for prompt in ("Old reject", "New reject"):
        _review(
            session,
            _question(session, env, prompt),
            ReviewDecision.REJECT,
            reasons=[RejectionReason.AMBIGUOUS],
        )

    found = _examples(session, env)

    assert found.accepted == []
    assert found.rejected is not None and found.rejected.text == "New reject"


def test_a_question_counts_by_its_latest_review(session: Session, env: SimpleNamespace) -> None:
    row = _question(session, env, "Approved, then rejected")
    _review(session, row, ReviewDecision.APPROVE)
    _review(session, row, ReviewDecision.REJECT, reasons=[RejectionReason.POOR_WORDING])

    found = _examples(session, env)

    assert found.accepted == []
    assert found.rejected is not None and found.rejected.text == "Approved, then rejected"


def test_a_deleted_review_takes_its_episode_and_it_is_never_retrieved(
    session: Session, env: SimpleNamespace
) -> None:
    approved = _question(session, env, "Approved while")
    rejected = _question(session, env, "Rejected while")
    keep = _review(session, _question(session, env, "Kept while"), ReviewDecision.APPROVE)
    gone = _review(session, approved, ReviewDecision.APPROVE)
    gone_reject = _review(
        session, rejected, ReviewDecision.REJECT, reasons=[RejectionReason.AMBIGUOUS]
    )
    gone_ids = [gone.id, gone_reject.id]
    outcomes = select(func.count()).select_from(ReviewOutcomeRow)
    assert session.scalar(outcomes.where(ReviewOutcomeRow.review_id.in_(gone_ids))) == 2

    delete_review(session, gone.id)
    delete_review(session, gone_reject.id)
    session.commit()

    assert [episode.review_id for episode in _episodes(session)] == [keep.id]
    assert session.scalar(outcomes.where(ReviewOutcomeRow.review_id.in_(gone_ids))) == 0
    assert session.get(ProfessorReviewRow, gone.id) is None
    found = _examples(session, env, MarkerEmbedder())
    assert _texts(found.accepted) == ["Kept while"]
    assert found.rejected is None


def test_an_episode_left_behind_by_a_bulk_delete_is_still_never_retrieved(
    session: Session, env: SimpleNamespace
) -> None:
    """SQLite enforces no ``ondelete``: retrieval itself requires the review to exist."""
    review = _review(session, _question(session, env, "Orphaned"), ReviewDecision.APPROVE)
    session.execute(text("DELETE FROM professor_reviews WHERE id = :id"), {"id": review.id})
    session.commit()
    session.expire_all()

    assert len(_episodes(session)) == 1
    assert _examples(session, env).accepted == []


def test_another_courses_episodes_are_never_retrieved(
    session: Session, env: SimpleNamespace
) -> None:
    """Same subject preset, different owner; and another subject: both are other memory."""
    other_owner = _course(session, "Python B")
    other_owner.course.owner_id = uuid.uuid4()
    physics = _course(session, "Physics", subject="physics")
    session.commit()
    for other in (other_owner, physics):
        _review(
            session,
            _question(session, other, f"Foreign while {other.course.name}"),
            ReviewDecision.APPROVE,
        )
        _review(
            session,
            _question(session, other, f"Foreign reject {other.course.name}"),
            ReviewDecision.REJECT,
            reasons=[RejectionReason.AMBIGUOUS],
        )
    _review(session, _question(session, env, "Own while"), ReviewDecision.APPROVE)

    found = _examples(session, env, MarkerEmbedder())

    assert _texts(found.accepted) == ["Own while"]
    assert found.rejected is None
    # A second course of the same professor and preset shares the memory (ADR-059).
    sibling = _course(session, "Python A2")
    sibling_found = rounds_module.accepted_examples(
        session, sibling.version.id, (sibling.while_loops.id, Difficulty.MEDIUM), MCQ
    )
    assert _texts(sibling_found.style_only) == ["Own while"]


# ------------------------------------------------------------------ migration


def test_the_migration_backfills_one_episode_per_existing_review(
    engine: Engine, session: Session, env: SimpleNamespace
) -> None:
    approved = _question(session, env, "Approved q", content={"code": "x = 1"})
    edited = _question(session, env, "Generated q")
    rejected = _question(session, env, "Rejected q")
    first = _review(session, approved, ReviewDecision.APPROVE, comment="Nice.")
    _review(
        session, edited, ReviewDecision.EDIT, prompt="Edited q", reference_solution="", tests=""
    )
    _review(
        session,
        rejected,
        ReviewDecision.REJECT,
        reasons=[RejectionReason.TOO_EASY],
        corrected_difficulty=Difficulty.EASY,
    )
    _review(session, approved, ReviewDecision.APPROVE)
    session.close()

    with engine.begin() as connection:
        command.downgrade(_alembic_config(connection), "0014_question_embeddings")
        assert connection.scalar(text("SELECT count(*) FROM professor_reviews")) == 4
    init_db(engine)

    with Session(engine) as reopened:
        episodes = list(
            reopened.scalars(select(MemoryEpisodeRow).order_by(MemoryEpisodeRow.review_id))
        )
        review_ids = list(
            reopened.scalars(select(ProfessorReviewRow.id).order_by(ProfessorReviewRow.id))
        )
        assert [episode.review_id for episode in episodes] == review_ids
        by_question = {}
        for episode in episodes:
            by_question.setdefault(episode.question_id, []).append(episode)
        (approve_1, approve_2) = by_question[approved.id]
        assert approve_1.review_id == first.id
        assert approve_1.text == "Approved q\nx = 1"
        assert approve_1.comment == "Nice." and approve_2.comment is None
        assert approve_1.subject == f"intro_python@{OWNER.hex}"
        assert approve_1.judge_verdicts["difficulty"]["passed"] is False
        assert approve_1.rubric_version == "rubric-test"
        (edit,) = by_question[edited.id]
        assert (edit.decision, edit.text, edit.original_text) == (
            ReviewDecision.EDIT,
            "Edited q",
            "Generated q",
        )
        (reject,) = by_question[rejected.id]
        assert reject.reasons == [RejectionReason.TOO_EASY]
        assert (reject.difficulty, reject.corrected_difficulty) == (
            Difficulty.MEDIUM,
            Difficulty.EASY,
        )
        assert reject.subtopic_ids == [env.while_loops.id]
        assert reject.question_type is MCQ
