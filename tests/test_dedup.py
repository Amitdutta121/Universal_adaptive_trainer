"""Duplicate detection: coverage Generate flags (m3) and the shared checker (ADR-063 point 6).

After a coverage run dedup is a soft flag, never a gate: these tests check the comparison pool
(same topic, approved/validation-passed only) and the threshold, and that a flagging failure
never takes the generation run down with it. The checker tests cover the compared text (code
included), exact matches, and the ``question_embeddings`` cache.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from llm_fakes import MetricJudgeClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_coverage import KeywordEmbedder, SubtopicRow, _gen_book, _gen_taxonomy, _mcq

from app.config import Settings
from app.domain.enums import Difficulty, QuestionStatus, RejectionReason, ReviewDecision
from app.domain.questions import Question
from app.persistence.models import (
    ProfessorReviewRow,
    QuestionEmbeddingRow,
    QuestionRow,
    QuestionSimilarityRow,
)
from app.retrieval import SectionEmbeddingStore
from app.retrieval.duplicates import (
    DUPLICATE_THRESHOLD,
    EXACT_MATCH_MODEL,
    DuplicateChecker,
    embed_text,
)
from app.web.routes.api.coverage import run_generation_for_gaps
from app.web.routes.api.dedup import flag_possible_duplicates
from app.web.routes.api.schemas import CoverageTargetRef


def _question(
    session: Session,
    *,
    topic_id: int,
    prompt: str,
    options: list[str] | None = None,
    code: str | None = None,
    status: QuestionStatus = QuestionStatus.VALIDATION_PASSED,
) -> QuestionRow:
    content: dict[str, object] = {}
    if options:
        content["options"] = options
    if code:
        content["code"] = code
    row = QuestionRow(
        prompt=prompt,
        topic_id=topic_id,
        status=status,
        content=content or None,
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


# ------------------------------------------------------------------ shared checker (ADR-063)

OUTPUT_STEM = "What will be the output of the following Python code snippet?"


class TokenEmbedder:
    """Bag of words over a fixed vocabulary, counting whole tokens; records every call."""

    model = "token-test-v1"
    VOCAB = ("output", "python", "code", "range", "print", "len", "for", "s")

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vectors = []
        for text in texts:
            tokens = re.findall(r"\w+", text.lower())
            vectors.append([float(tokens.count(word)) for word in self.VOCAB])
        return vectors


def test_the_compared_text_includes_the_code() -> None:
    text = embed_text(OUTPUT_STEM, {"code": "print(len('abc'))", "options": ["3", "4"]})
    assert text.splitlines() == [OUTPUT_STEM, "print(len('abc'))", "3", "4"]


def test_same_stem_with_different_code_is_not_flagged(session: Session) -> None:
    """21 output-prediction questions share one stem; only their code tells them apart."""
    _question(session, topic_id=1, prompt=OUTPUT_STEM, code="for i in range(3): print(i)")
    new = _question(session, topic_id=1, prompt=OUTPUT_STEM, code="s = 'abc'; print(len(s))")

    assert flag_possible_duplicates(session, TokenEmbedder(), [new]) == 0
    assert list(session.scalars(select(QuestionSimilarityRow))) == []


def test_same_stem_and_same_code_is_a_duplicate(session: Session) -> None:
    existing = _question(session, topic_id=1, prompt=OUTPUT_STEM, code="print(len('ab'))")

    (match,) = DuplicateChecker(session, TokenEmbedder()).similar(
        topic_id=1, prompt=OUTPUT_STEM, content={"code": "print(len('ab'))"}
    )

    assert (match.question_id, match.exact, match.duplicate) == (existing.id, True, True)
    assert OUTPUT_STEM in match.text and "print(len('ab'))" in match.text


def test_an_exact_match_ignores_case_and_whitespace_and_needs_no_embedder(
    session: Session,
) -> None:
    existing = _question(session, topic_id=1, prompt="Which loop repeats while a condition holds?")

    (match,) = DuplicateChecker(session, None)(
        Question(topic_id=1, prompt="  which loop   REPEATS while a condition holds? ")
    )

    assert (match.question_id, match.exact, match.score) == (existing.id, True, 1.0)
    assert match.model == EXACT_MATCH_MODEL
    assert not DuplicateChecker(session, None)(Question(topic_id=1, prompt="Another question?"))


def test_candidate_vectors_are_stored_once(session: Session) -> None:
    """The first check embeds the new text and every candidate in one call; later checks
    embed only the new text, until a candidate's text changes."""
    first = _question(session, topic_id=1, prompt="Print range output", code="print(range(2))")
    _question(session, topic_id=1, prompt="Len of s", code="print(len(s))")
    embedder = TokenEmbedder()
    checker = DuplicateChecker(session, embedder)

    checker.similar(topic_id=1, prompt="Python for loop", content=None)
    checker.similar(topic_id=1, prompt="Python code output", content=None)
    first.prompt = "Edited prompt"
    session.commit()
    checker.similar(topic_id=1, prompt="Python code", content=None)

    assert [len(call) for call in embedder.calls] == [3, 1, 2]
    assert embedder.calls[2][1].startswith("Edited prompt")
    stored = list(session.scalars(select(QuestionEmbeddingRow)))
    assert len(stored) == 2 and {row.model for row in stored} == {TokenEmbedder.model}


def test_an_embedder_failure_inside_a_round_falls_back_to_exact_matches(
    session: Session,
) -> None:
    existing = _question(session, topic_id=1, prompt="Which loop repeats?")

    class FailingEmbedder:
        model = "failing"

        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise RuntimeError("embedder unavailable")

    (match,) = DuplicateChecker(session, FailingEmbedder())(
        Question(topic_id=1, prompt="Which loop repeats?")
    )
    assert match.question_id == existing.id and match.exact


def test_the_calibration_script_prints_the_threshold_table(
    session: Session, settings: Settings
) -> None:
    """scripts/calibrate_dedup.py on the test DB with a fake embedder: no provider call."""
    from scripts.calibrate_dedup import calibrate, load_questions

    first = _question(session, topic_id=1, prompt=OUTPUT_STEM, code="print(range(3))")
    copy = _question(session, topic_id=1, prompt=OUTPUT_STEM, code="print(range(3))")
    other = _question(session, topic_id=1, prompt=OUTPUT_STEM, code="s = 'ab'; print(len(s))")
    for row, decision, reasons in (
        (first, ReviewDecision.APPROVE, []),
        (copy, ReviewDecision.REJECT, [RejectionReason.TOO_SIMILAR_REPETITIVE]),
        (other, ReviewDecision.APPROVE, []),
    ):
        session.add(ProfessorReviewRow(question_id=row.id, decision=decision, reasons=reasons))
    session.commit()

    db_path = Path(session.get_bind().url.database)
    report = calibrate(load_questions(db_path), TokenEmbedder())

    assert "compare text: prompt + code + options" in report
    rows = [line.split() for line in report.splitlines() if line.startswith("  0.75")]
    # Same topic, then same version: the copy is caught, the different-code question is not.
    assert rows == [["0.75", "1/1", "0/1", "0/0"]] * 2
