"""Post-generation duplicate flagging (coverage Generate m3).

Dedup is a soft flag, never a gate: these tests check the comparison pool
(same topic, approved/validation-passed only) and the threshold, and that a
flagging failure never takes the generation run down with it.
"""

from __future__ import annotations

from llm_fakes import MetricJudgeClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_coverage import KeywordEmbedder, SubtopicRow, _gen_book, _gen_taxonomy, _mcq

from app.config import Settings
from app.domain.enums import Difficulty, QuestionStatus
from app.persistence.models import QuestionRow, QuestionSimilarityRow
from app.retrieval import SectionEmbeddingStore
from app.web.routes.api.coverage import run_generation_for_gaps
from app.web.routes.api.dedup import DUPLICATE_THRESHOLD, flag_possible_duplicates
from app.web.routes.api.schemas import CoverageTargetRef


def _question(
    session: Session,
    *,
    topic_id: int,
    prompt: str,
    options: list[str] | None = None,
    status: QuestionStatus = QuestionStatus.VALIDATION_PASSED,
) -> QuestionRow:
    row = QuestionRow(
        prompt=prompt,
        topic_id=topic_id,
        status=status,
        content={"options": options} if options else None,
        generator_name="test-gen",
        generator_version="1",
    )
    session.add(row)
    session.commit()
    return row


def test_a_near_copy_is_flagged_against_the_earlier_question(session: Session) -> None:
    existing = _question(
        session,
        topic_id=1,
        prompt="Which loop repeats while a condition holds?",
        options=["while loop", "for loop", "do loop", "no loop"],
    )
    new = _question(
        session,
        topic_id=1,
        prompt="Which loop repeats while a condition holds?",
        options=["while loop", "for loop", "do loop", "no loop"],
    )

    flag_possible_duplicates(session, KeywordEmbedder(), [new])

    flags = list(session.scalars(select(QuestionSimilarityRow)))
    assert len(flags) == 1
    assert flags[0].question_id == new.id
    assert flags[0].similar_question_id == existing.id
    assert flags[0].score >= DUPLICATE_THRESHOLD
    assert flags[0].model == KeywordEmbedder.model


def test_an_unrelated_question_is_not_flagged(session: Session) -> None:
    _question(session, topic_id=1, prompt="A variable is a name. variable variable.")
    new = _question(session, topic_id=1, prompt="A while loop repeats while true. loop loop.")

    flag_possible_duplicates(session, KeywordEmbedder(), [new])

    assert list(session.scalars(select(QuestionSimilarityRow))) == []


def test_no_cross_topic_flags_even_for_identical_text(session: Session) -> None:
    _question(session, topic_id=1, prompt="Which loop repeats while a condition holds?")
    new = _question(session, topic_id=2, prompt="Which loop repeats while a condition holds?")

    flag_possible_duplicates(session, KeywordEmbedder(), [new])

    assert list(session.scalars(select(QuestionSimilarityRow))) == []


def test_rejected_and_generated_questions_are_never_compared_against(session: Session) -> None:
    for status in (
        QuestionStatus.REJECTED,
        QuestionStatus.GENERATED,
        QuestionStatus.VALIDATION_FAILED,
    ):
        _question(
            session,
            topic_id=1,
            prompt="Which loop repeats while a condition holds?",
            status=status,
        )
    new = _question(session, topic_id=1, prompt="Which loop repeats while a condition holds?")

    flag_possible_duplicates(session, KeywordEmbedder(), [new])

    assert list(session.scalars(select(QuestionSimilarityRow))) == []


def test_a_question_alone_in_its_topic_costs_no_embedder_call(session: Session) -> None:
    """No candidates means no comparison is possible -- skip rather than call
    the provider for nothing."""
    new = _question(session, topic_id=1, prompt="Anything.")

    class ExplodingEmbedder:
        model = "should-not-be-called"

        def embed(self, texts: list[str]) -> list[list[float]]:
            raise AssertionError("embedder should not be called with no candidates")

    flag_possible_duplicates(session, ExplodingEmbedder(), [new])

    assert list(session.scalars(select(QuestionSimilarityRow))) == []


class _FlaggingRaisesEmbedder(KeywordEmbedder):
    """Behaves normally for a single retrieval query, but fails once asked to
    compare several texts -- the shape a real flagging call always takes."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > 1:
            raise RuntimeError("embedder unavailable")
        return super().embed(texts)


def test_a_flagging_failure_never_fails_the_generation_run(
    session: Session, settings: Settings
) -> None:
    book = _gen_book(session, settings)
    env = _gen_taxonomy(session, book.id)
    SectionEmbeddingStore(session, KeywordEmbedder()).backfill()
    session.commit()

    topic_id = session.get(SubtopicRow, env.while_loops.id).topic_id
    _question(
        session,
        topic_id=topic_id,
        prompt="Which loop repeats while a condition holds?",
        status=QuestionStatus.APPROVED,
    )
    client = MetricJudgeClient(draft=_mcq(env.while_loops.topic_id, env.while_loops.id))

    result = run_generation_for_gaps(
        session,
        [CoverageTargetRef(subtopic_id=env.while_loops.id, difficulty=Difficulty.MEDIUM)],
        embedder=_FlaggingRaisesEmbedder(),
        client=client,
    )

    assert result.generated and not result.failed
    assert list(session.scalars(select(QuestionSimilarityRow))) == []
