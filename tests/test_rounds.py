"""Question setup rounds (docs/QUESTION_SETUP_PLAN.md, agent B).

Round questions are judged inside the retry loop and dropped after the last attempt; rounds
target only cells below their target and draw styles by reject-weighted chance; ``run_round``
moves a round through its statuses; the routes queue and report a round.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import book_documents as docs
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient
from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.enums import (
    CurriculumStatus,
    CustomJudgeKind,
    Difficulty,
    QuestionStatus,
    QuestionType,
    ReviewDecision,
    RoundStatus,
)
from app.errors import DomainRuleError, LLMRequestError
from app.evaluation import DifficultyVerdict, GeneratabilityVerdict
from app.evaluation import custom as custom_module
from app.evaluation.custom import CustomJudgeResult
from app.feedback import submit_review
from app.generation import rounds as rounds_module
from app.generation.attempts import MAX_GENERATION_ATTEMPTS
from app.generation.prompts import (
    RejectedExample,
    RoundExamples,
    ShownExample,
    build_prompt,
    render_round_target,
)
from app.generation.rounds import (
    next_round,
    plan_targets,
    run_round,
    start_round,
    style_weights,
)
from app.generation.schemas import MultipleChoiceDraft
from app.generation.spec import QuestionSpec
from app.ingestion import BookImportService
from app.persistence.models import (
    CurriculumVersionRow,
    CustomJudgeRow,
    GenerationRoundRow,
    ProfessorReviewRow,
    QuestionEvaluationRow,
    QuestionRow,
    QuestionSetupRow,
    QuestionSimilarityRow,
    SubtopicEvidenceRow,
    SubtopicRow,
    TopicRow,
)
from app.persistence.repositories import BookStructureRepository, GenerationRoundRepository
from app.retrieval import SectionEmbeddingStore
from app.retrieval.examples import EXAMPLE_PAIR_THRESHOLD
from app.styles import QuestionStyle
from app.web.routes.api.coverage import get_generation_client

# ------------------------------------------------------------------ fixtures


def _style(style_id: str, name: str) -> QuestionStyle:
    example = {"prompt": "Which loop repeats while a condition holds?", "answer": "while"}
    return QuestionStyle(
        id=style_id,
        subject="intro_python",
        name=name,
        summary=f"{name}: pick the one right option.",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty_range=[Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD],
        checked_by="Compares the chosen option with the key",
        examples=(example, example),
    )


STYLE_A = _style("py.concept_choice", "Pick the right concept")
STYLE_B = _style("py.code_choice", "Pick what the code does")
LIBRARY = [STYLE_A, STYLE_B]


@pytest.fixture(autouse=True)
def fake_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent A owns the real library; these tests run against two fake styles."""
    import app.styles

    monkeypatch.setattr(rounds_module, "get_library", lambda subject: list(LIBRARY))
    monkeypatch.setattr(app.styles, "get_library", lambda subject: list(LIBRARY))


class KeywordEmbedder:
    """Bag-of-words embedder, as in tests/test_coverage.py."""

    model = "keyword-test-v1"
    VOCAB = ("loop", "while", "range", "variable", "string", "slice")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) for word in self.VOCAB] for t in texts]


def _book(session: Session, settings: Settings):
    sections = [
        "A while loop repeats while a condition holds. Use a while loop to loop again.",
        "A string can be sliced. Take a slice of a string. string slice string.",
    ]
    doc = {
        "schema_version": "1",
        "title": "Round Book",
        "chapters": [{"sections": [{"text": text} for text in sections]}],
    }
    book = BookImportService(session, settings).import_upload(
        filename="round_book.json", data=docs.to_bytes(doc)
    )
    session.commit()
    return book


@pytest.fixture
def env(session: Session, settings: Settings) -> SimpleNamespace:
    book = _book(session, settings)
    version = CurriculumVersionRow(
        label="Rounds v1",
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
        source_book_ids=[book.id],
    )
    session.add(version)
    session.flush()
    loops = TopicRow(curriculum_version_id=version.id, name="Loops", position=0)
    strings = TopicRow(curriculum_version_id=version.id, name="Strings", position=1)
    session.add_all([loops, strings])
    session.flush()
    while_loops = SubtopicRow(
        topic_id=loops.id, name="While loops", description="Using a while loop.", position=0
    )
    slicing = SubtopicRow(
        topic_id=strings.id, name="Slicing", description="Taking a slice of a string.", position=0
    )
    session.add_all([while_loops, slicing])
    session.commit()
    SectionEmbeddingStore(session, KeywordEmbedder()).backfill()
    session.commit()
    sections = BookStructureRepository(session).sections_in_book(book.id)
    return SimpleNamespace(
        version=version,
        while_loops=while_loops,
        slicing=slicing,
        sections=sections,
        book=book,
    )


def _setup(
    session: Session,
    env: SimpleNamespace,
    cells: list[tuple[int, str, int]],
    styles: dict[int, list[str]] | None = None,
) -> QuestionSetupRow:
    styles = styles or {
        env.while_loops.id: [STYLE_A.id, STYLE_B.id],
        env.slicing.id: [STYLE_A.id],
    }
    setup = QuestionSetupRow(
        curriculum_version_id=env.version.id,
        approved_styles={str(k): v for k, v in styles.items()},
        cell_targets=[{"subtopic_id": s, "difficulty": d, "target": t} for s, d, t in cells],
    )
    session.add(setup)
    session.commit()
    return setup


def _question(
    session: Session,
    env: SimpleNamespace,
    subtopic: SubtopicRow,
    difficulty: str,
    status: QuestionStatus,
    *,
    style_id: str | None = None,
    prompt: str = "Q?",
    question_type: QuestionType | None = None,
) -> QuestionRow:
    row = QuestionRow(
        curriculum_version_id=env.version.id,
        topic_id=subtopic.topic_id,
        subtopic_ids=[subtopic.id],
        difficulty=Difficulty(difficulty),
        status=status,
        prompt=prompt,
        question_type=question_type,
        style_id=style_id,
        target_subtopic_id=subtopic.id if style_id else None,
    )
    session.add(row)
    session.commit()
    return row


def _professor_approved(session: Session, row: QuestionRow) -> QuestionRow:
    """Approve ``row`` through a review: examples are read from its memory episode."""
    submit_review(session, question_id=row.id, decision=ReviewDecision.APPROVE)
    session.commit()
    return row


def _mcq(topic_id: int, subtopic_id: int) -> MultipleChoiceDraft:
    return MultipleChoiceDraft(
        topic_id=topic_id,
        subtopic_ids=[subtopic_id],
        prompt="Which loop repeats while a condition holds?",
        options=["while loop", "for loop", "do loop", "no loop"],
        correct_option_index=0,
        explanation="A while loop runs while its condition is true.",
    )


class DifficultySequenceClient(MetricJudgeClient):
    """Answers the difficulty judge from a sequence (the last answer repeats)."""

    def __init__(self, *, difficulties: list[Difficulty], **kwargs: Any) -> None:
        super().__init__(difficulty=difficulties[0], **kwargs)
        self.difficulties = difficulties
        self.difficulty_calls = 0

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        if response_model is DifficultyVerdict:
            self.difficulty = self.difficulties[
                min(self.difficulty_calls, len(self.difficulties) - 1)
            ]
            self.difficulty_calls += 1
        return super().complete_structured(
            system=system, prompt=prompt, response_model=response_model, **kwargs
        )


def _queue(session: Session, setup: QuestionSetupRow, targets: list[dict]) -> GenerationRoundRow:
    row = GenerationRoundRepository(session).add(
        GenerationRoundRow(setup_id=setup.id, number=1, targets=targets, requested=len(targets))
    )
    session.commit()
    return row


def _run(engine: Engine, round_id: int, client: object, embedder: object = None) -> None:
    run_round(
        round_id,
        client=client,  # type: ignore[arg-type]
        embedder=embedder or KeywordEmbedder(),  # type: ignore[arg-type]
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )


def _round(engine: Engine, round_id: int) -> GenerationRoundRow:
    with Session(engine) as fresh:
        return fresh.get(GenerationRoundRow, round_id)


def _round_questions(engine: Engine, round_id: int) -> list[QuestionRow]:
    with Session(engine) as fresh:
        return list(
            fresh.scalars(
                select(QuestionRow).where(
                    QuestionRow.round_id == round_id, QuestionRow.audit.is_(False)
                )
            )
        )


def _target(env: SimpleNamespace, difficulty: str = "medium", style: str = STYLE_A.id) -> dict:
    return {"subtopic_id": env.while_loops.id, "difficulty": difficulty, "style_id": style}


# ------------------------------------------------------------------ retry loop


def test_a_judge_failure_is_retried_with_its_reason_then_stored(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 3)])
    row = _queue(session, setup, [_target(env, "easy")])
    client = DifficultySequenceClient(
        difficulties=[Difficulty.HARD, Difficulty.EASY],
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
    )

    _run(engine, row.id, client)

    assert len(client.generation_calls) == 2
    retry_prompt = client.generation_calls[1]["prompt"]
    assert "--- correction ---" in retry_prompt
    assert "difficulty_judge" in retry_prompt and "must be easy" in retry_prompt
    first_prompt = client.generation_calls[0]["prompt"]
    assert "--- target ---" in first_prompt
    assert f"[subtopic {env.while_loops.id}] While loops" in first_prompt
    assert STYLE_A.name in first_prompt and STYLE_A.checked_by in first_prompt

    (question,) = _round_questions(engine, row.id)
    assert question.style_id == STYLE_A.id
    assert question.target_subtopic_id == env.while_loops.id
    assert question.status is QuestionStatus.VALIDATION_PASSED
    assert question.spec["target_subtopic_id"] == env.while_loops.id
    assert [check.name for check in question.generation_attempts[0].failed_checks] == [
        "difficulty_judge"
    ]
    assert question.generation_attempts[-1].usable
    assert question.pedagogical_eval["metrics"]
    done = _round(engine, row.id)
    assert (done.status, done.produced, done.dropped) == (RoundStatus.DONE, 1, 0)
    assert done.first_attempt_passed == 0


def test_the_round_counts_targets_that_passed_on_their_first_attempt(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    from app.web.routes.api.schemas import GenerationRoundOut

    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    row = _queue(session, setup, [_target(env)])
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )

    _run(engine, row.id, client)

    done = _round(engine, row.id)
    assert (done.produced, done.first_attempt_passed) == (1, 1)
    assert GenerationRoundOut.from_row(done).first_attempt_passed == 1
    # Rounds from before the count say nothing rather than zero.
    assert GenerationRoundOut.from_row(row).first_attempt_passed is None


def test_a_hard_cell_hardens_a_question_that_passed_the_answer_check(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    """A hard cell first stores nothing from a medium question that passes, then makes it harder."""
    setup = _setup(session, env, [(env.while_loops.id, "hard", 1)])
    row = _queue(session, setup, [_target(env, "hard")])
    client = DifficultySequenceClient(
        difficulties=[Difficulty.EASY, Difficulty.HARD],
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
    )

    _run(engine, row.id, client)

    prompts = [call["prompt"] for call in client.generation_calls]
    assert "Create a medium " in prompts[0]
    assert "--- make it harder ---" not in prompts[0]
    assert "Create a hard " in prompts[1]
    assert "--- make it harder ---" in prompts[1]
    assert "This question already passes the answer check." in prompts[1]
    assert "Which loop repeats while a condition holds?" in prompts[1]
    # The seed is not judged. The first harder draft is easy, so it is retried once.
    assert client.difficulty_calls == 2
    assert len(prompts) == 3
    (question,) = _round_questions(engine, row.id)
    assert question.difficulty is Difficulty.HARD
    assert question.status is QuestionStatus.VALIDATION_PASSED
    done = _round(engine, row.id)
    assert (done.status, done.produced, done.dropped) == (RoundStatus.DONE, 1, 0)


def test_a_hard_cell_does_not_harden_a_question_that_fails_the_answer_check(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "hard", 1)])
    row = _queue(session, setup, [_target(env, "hard")])
    draft = _mcq(env.while_loops.topic_id, env.while_loops.id)
    draft.options = ["same", "same", "other", "else"]
    client = DifficultySequenceClient(difficulties=[Difficulty.HARD], draft=draft)

    _run(engine, row.id, client)

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    assert client.difficulty_calls == 0
    assert all("--- make it harder ---" not in call["prompt"] for call in client.generation_calls)
    assert _round_questions(engine, row.id) == []
    done = _round(engine, row.id)
    assert (done.produced, done.dropped) == (0, 1)


def test_a_hard_cell_the_lesson_cannot_support_is_skipped(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "hard", 1)])
    row = _queue(session, setup, [_target(env, "hard")])
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        should_have_generated=False,
    )

    _run(engine, row.id, client)

    assert client.generation_calls == []
    assert _round_questions(engine, row.id) == []
    done = _round(engine, row.id)
    assert (done.status, done.produced, done.dropped, done.skipped) == (RoundStatus.DONE, 0, 0, 1)
    assert done.skip_reason


def test_a_hard_cell_still_generates_when_the_generatability_judge_cannot_answer(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    class SilentGeneratability(MetricJudgeClient):
        def complete_structured(self, *, response_model, **kwargs):
            if response_model is GeneratabilityVerdict:
                raise LLMRequestError("Generatability judge unavailable")
            return super().complete_structured(response_model=response_model, **kwargs)

    setup = _setup(session, env, [(env.while_loops.id, "hard", 1)])
    row = _queue(session, setup, [_target(env, "hard")])
    client = SilentGeneratability(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty.HARD,
    )

    _run(engine, row.id, client)

    assert client.generation_calls
    done = _round(engine, row.id)
    assert done.skipped == 0
    assert done.produced == 1


def test_a_question_still_failing_after_the_last_attempt_is_dropped(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 3)])
    row = _queue(session, setup, [_target(env, "easy")])
    client = DifficultySequenceClient(
        difficulties=[Difficulty.HARD],
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
    )

    _run(engine, row.id, client)

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    assert _round_questions(engine, row.id) == []
    with Session(engine) as fresh:
        audits = list(fresh.scalars(select(QuestionRow).where(QuestionRow.audit.is_(True))))
    assert len(audits) == 1
    assert audits[0].audit_metric == "difficulty"
    done = _round(engine, row.id)
    assert (done.status, done.produced, done.dropped) == (RoundStatus.DONE, 0, 1)


def test_a_topic_judge_that_names_another_subtopic_fails_the_attempt(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    row = _queue(session, setup, [_target(env)])
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty.MEDIUM,
        topic_id=env.slicing.topic_id,
        subtopic_ids=[env.slicing.id],
    )

    _run(engine, row.id, client)

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    assert "topic_judge" in client.generation_calls[1]["prompt"]
    assert _round(engine, row.id).dropped == 1


def test_a_failed_custom_rule_is_retried_and_its_results_are_stored(
    session: Session, engine: Engine, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    rule = CustomJudgeRow(curriculum_version_id=env.version.id, rule_text="No global variables")
    disabled = CustomJudgeRow(
        curriculum_version_id=env.version.id, rule_text="Disabled rule", enabled=False
    )
    session.add_all([rule, disabled])
    session.commit()
    row = _queue(session, setup, [_target(env)])
    calls: list[list[str]] = []

    def fake_run(question, rules, *, client=None):
        calls.append([r.rule_text for r in rules])
        passed = len(calls) > 1
        return [
            CustomJudgeResult(
                judge_id=r.id,
                rule_text=r.rule_text,
                kind=r.kind,
                passed=passed,
                reason=None if passed else "It uses a global counter.",
            )
            for r in rules
        ]

    monkeypatch.setattr(custom_module, "run_custom_judges", fake_run)
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )

    _run(engine, row.id, client)

    assert calls == [["No global variables"], ["No global variables"]]
    assert "It uses a global counter." in client.generation_calls[1]["prompt"]
    (question,) = _round_questions(engine, row.id)
    with Session(engine) as fresh:
        evaluation = fresh.scalars(
            select(QuestionEvaluationRow).where(QuestionEvaluationRow.question_id == question.id)
        ).one()
    assert evaluation.custom_results[0]["passed"] is True
    assert evaluation.custom_results[0]["rule_text"] == "No global variables"


def test_section_only_generation_keeps_its_spec_and_prompt() -> None:
    spec = QuestionSpec(
        curriculum_version_id=1,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=Difficulty.EASY,
        source_section_ids=[3],
    )
    assert spec.stored() == {
        "curriculum_version_id": 1,
        "question_type": "multiple_choice",
        "difficulty": "easy",
        "source_section_ids": [3],
        "seed": None,
    }
    _, plain = build_prompt(spec, section_text="text", citation="c", taxonomy="t")
    assert "--- target ---" not in plain
    _, aimed = build_prompt(
        spec, section_text="text", citation="c", taxonomy="t", target_block="--- target ---\nX"
    )
    assert aimed.replace("\n\n--- target ---\nX", "") == plain
    assert "One taught step, applied directly." in plain
    assert "Two or three taught ideas combined" in plain
    assert "Several taught ideas composed" in plain


# ------------------------------------------------------------------ planning


def test_only_cells_below_target_get_targets(session: Session, env: SimpleNamespace) -> None:
    setup = _setup(
        session,
        env,
        [
            (env.while_loops.id, "easy", 2),
            (env.while_loops.id, "medium", 1),
            (env.slicing.id, "easy", 1),
        ],
    )
    # while/easy: one approved + one pending = full. slicing/easy: a reject does not count.
    _question(session, env, env.while_loops, "easy", QuestionStatus.APPROVED)
    _question(session, env, env.while_loops, "easy", QuestionStatus.VALIDATION_PASSED)
    _question(session, env, env.slicing, "easy", QuestionStatus.REJECTED)

    targets = plan_targets(session, setup, size=10, rng=random.Random(0))

    cells = sorted((t["subtopic_id"], t["difficulty"]) for t in targets)
    assert cells == sorted([(env.while_loops.id, "medium"), (env.slicing.id, "easy")])


def test_targets_spread_across_cells_before_repeating_one(
    session: Session, env: SimpleNamespace
) -> None:
    setup = _setup(
        session,
        env,
        [(env.while_loops.id, "easy", 3), (env.slicing.id, "hard", 3)],
    )

    two = plan_targets(session, setup, size=2, rng=random.Random(0))
    everything = plan_targets(session, setup, size=10, rng=random.Random(0))

    assert {(t["subtopic_id"], t["difficulty"]) for t in two} == {
        (env.while_loops.id, "easy"),
        (env.slicing.id, "hard"),
    }
    assert len(everything) == 6


def test_a_subtopic_without_approved_styles_gets_no_targets(
    session: Session, env: SimpleNamespace
) -> None:
    setup = _setup(
        session,
        env,
        [(env.while_loops.id, "easy", 1), (env.slicing.id, "easy", 1)],
        styles={env.while_loops.id: [STYLE_A.id], env.slicing.id: ["py.not_in_library"]},
    )
    targets = plan_targets(session, setup, size=10)
    assert [t["subtopic_id"] for t in targets] == [env.while_loops.id]


def test_style_weights_halve_per_reject_and_exclude_at_two() -> None:
    assert style_weights(["a", "b", "c"], {"b": 1, "c": 2}) == {"a": 1.0, "b": 0.5, "c": 0.0}


def test_when_every_style_is_excluded_the_least_rejected_is_used() -> None:
    assert style_weights(["a", "b"], {"a": 3, "b": 2}) == {"a": 0.0, "b": 1.0}


def test_a_style_rejected_twice_in_a_cell_is_not_drawn_there(
    session: Session, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 6), (env.while_loops.id, "hard", 6)])
    for _ in range(2):
        _question(
            session, env, env.while_loops, "easy", QuestionStatus.REJECTED, style_id=STYLE_A.id
        )

    drawn: dict[str, set[str]] = {"easy": set(), "hard": set()}
    for seed in range(10):
        for target in plan_targets(session, setup, size=12, rng=random.Random(seed)):
            drawn[target["difficulty"]].add(target["style_id"])

    assert drawn["easy"] == {STYLE_B.id}
    # The rejects belong to the easy cell only.
    assert drawn["hard"] == {STYLE_A.id, STYLE_B.id}


def test_next_round_refuses_while_a_round_is_running(
    session: Session, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 2)])
    first = start_round(session, setup.id, size=1)
    session.commit()
    assert (first.number, first.status, first.requested) == (1, RoundStatus.QUEUED, 1)

    with pytest.raises(DomainRuleError):
        next_round(session, setup.id)
    with pytest.raises(DomainRuleError):
        start_round(session, setup.id)

    first.status = RoundStatus.DONE
    session.commit()
    second = next_round(session, setup.id, size=5)
    assert (second.number, second.requested) == (2, 2)


def test_a_full_setup_gets_an_empty_done_round(session: Session, env: SimpleNamespace) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "easy", 1)])
    _question(session, env, env.while_loops, "easy", QuestionStatus.APPROVED)

    row = next_round(session, setup.id)

    assert (row.status, row.requested, row.targets) == (RoundStatus.DONE, 0, [])


# ------------------------------------------------------------------ run_round


def test_run_round_reports_progress_and_examples(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 4)])
    _professor_approved(
        session,
        _question(
            session,
            env,
            env.while_loops,
            "medium",
            QuestionStatus.APPROVED,
            prompt="Accepted: what does a while loop do?",
            question_type=QuestionType.MULTIPLE_CHOICE,
        ),
    )
    row = start_round(session, setup.id, size=2, rng=random.Random(1))
    session.commit()
    assert row.status is RoundStatus.QUEUED
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )

    _run(engine, row.id, client)

    done = _round(engine, row.id)
    assert (done.status, done.requested, done.produced, done.dropped) == (
        RoundStatus.DONE,
        2,
        2,
        0,
    )
    assert done.started_at is not None and done.finished_at is not None
    assert (
        "Example 1: Accepted: what does a while loop do?" in (client.generation_calls[0]["prompt"])
    )
    questions = _round_questions(engine, row.id)
    assert len(questions) == 2
    assert {q.spec["source_section_ids"][0] for q in questions} == {env.sections[0].id}

    # A second run of the same round is a no-op.
    _run(engine, row.id, client)
    assert len(_round_questions(engine, row.id)) == 2


def test_without_an_embedder_a_target_is_grounded_in_its_evidence(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    session.add(
        SubtopicEvidenceRow(
            subtopic_id=env.while_loops.id,
            book_id=env.book.id,
            section_id=env.sections[1].id,
            candidate_label="while",
        )
    )
    session.commit()
    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    row = _queue(session, setup, [_target(env)])
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )

    run_round(
        row.id,
        client=client,  # type: ignore[arg-type]
        embedder=None,
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )

    (question,) = _round_questions(engine, row.id)
    assert question.spec["source_section_ids"] == [env.sections[1].id]


def test_a_round_that_cannot_reach_a_model_ends_failed_with_a_reason(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    row = _queue(session, setup, [_target(env)])

    # No client and LLM_PROVIDER=none: building the live client is a configuration error.
    run_round(
        row.id,
        embedder=KeywordEmbedder(),  # type: ignore[arg-type]
        session_factory=lambda: Session(engine, expire_on_commit=False),
    )

    failed = _round(engine, row.id)
    assert failed.status is RoundStatus.FAILED
    assert failed.error
    assert failed.finished_at is not None


# ------------------------------------------------------------------ routes


@pytest.fixture
def http(configured_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    holder = SimpleNamespace(client=None)
    configured_app.dependency_overrides[get_generation_client] = lambda: holder.client
    monkeypatch.setattr(rounds_module, "default_embedder", KeywordEmbedder)
    with TestClient(configured_app) as test_client:
        holder.http = test_client
        yield holder


def test_post_rounds_queues_and_runs_the_next_round(
    http: SimpleNamespace, session: Session, env: SimpleNamespace
) -> None:
    setup = _setup(session, env, [(env.while_loops.id, "medium", 1)])
    http.client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )

    response = http.http.post("/api/rounds", json={"setup_id": setup.id})

    assert response.status_code == 202, response.text
    round_id = response.json()["round_id"]
    polled = http.http.get(f"/api/rounds/{round_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert (body["status"], body["requested"], body["produced"], body["dropped"]) == (
        "done",
        1,
        1,
        0,
    )

    full = http.http.post("/api/rounds", json={"setup_id": setup.id})
    assert full.status_code == 422
    assert full.json()["error"]["message"] == "Every cell has reached its target."
    session.expire_all()
    assert len(session.scalars(select(GenerationRoundRow)).all()) == 1


def test_round_routes_404_on_unknown_ids(http: SimpleNamespace) -> None:
    assert http.http.post("/api/rounds", json={"setup_id": 999}).status_code == 404
    assert http.http.get("/api/rounds/999").status_code == 404


def test_unavailable_required_judge_cannot_publish_round_question(session, engine, env):
    class UnavailableDifficulty(MetricJudgeClient):
        def complete_structured(self, *, response_model, **kwargs):
            if response_model is DifficultyVerdict:
                raise LLMRequestError("Difficulty judge unavailable")
            return super().complete_structured(response_model=response_model, **kwargs)

    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    row = _queue(session, setup, [_target(env)])
    client = UnavailableDifficulty(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty.MEDIUM,
        topic_id=env.while_loops.topic_id,
        subtopic_ids=[env.while_loops.id],
    )
    _run(engine, row.id, client)
    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    assert _round_questions(engine, row.id) == []
    assert _round(engine, row.id).dropped == 1


def test_real_library_and_custom_rule_run_through_refill_pipeline(
    session, engine, env, monkeypatch
):
    import app.styles
    from app.styles.library import get_library

    monkeypatch.setattr(rounds_module, "get_library", get_library)
    monkeypatch.setattr(app.styles, "get_library", get_library)
    style = next(
        s
        for s in get_library("intro_python")
        if s.question_type == QuestionType.MULTIPLE_CHOICE
        and Difficulty.MEDIUM in s.difficulty_range
    )
    setup = _setup(
        session, env, [(env.while_loops.id, "medium", 1)], styles={env.while_loops.id: [style.id]}
    )
    _question(session, env, env.while_loops, "medium", QuestionStatus.APPROVED)
    rule = CustomJudgeRow(
        curriculum_version_id=env.version.id,
        rule_text="No global declarations",
        kind=CustomJudgeKind.PATTERN,
        pattern="ast:Global",
    )
    session.add(rule)
    session.commit()
    assert plan_targets(session, setup, size=10) == []
    row = rounds_module.refill_round(
        session, setup.id, {(env.while_loops.id, Difficulty.MEDIUM): 1}
    )
    session.commit()
    client = MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id),
        difficulty=Difficulty.MEDIUM,
        topic_id=env.while_loops.topic_id,
        subtopic_ids=[env.while_loops.id],
    )
    _run(engine, row.id, client)
    (question,) = _round_questions(engine, row.id)
    assert question.style_id == style.id
    assert question.trust_provenance == "pending"
    assert question.status == QuestionStatus.VALIDATION_PASSED
    with Session(engine) as fresh:
        evaluation = fresh.scalars(
            select(QuestionEvaluationRow).where(QuestionEvaluationRow.question_id == question.id)
        ).one()
        assert evaluation.custom_results[0]["passed"] is True


def test_round_execution_claim_is_idempotent(session, engine, env, monkeypatch):
    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    row = _queue(session, setup, [_target(env)])
    calls = []
    monkeypatch.setattr(
        rounds_module, "_generate_round", lambda db, round_row, **kwargs: calls.append(round_row.id)
    )
    _run(engine, row.id, None)
    _run(engine, row.id, None)
    assert calls == [row.id]
    assert _round(engine, row.id).status == RoundStatus.DONE


# ------------------------------------------------------------------ duplicates (ADR-063 point 6)


class ScoredEmbedder(KeywordEmbedder):
    """Places the round's draft at a chosen cosine to the stored "Existing" question.

    Every other text (section retrieval) embeds as :class:`KeywordEmbedder` does. ``scores``
    is consumed one per check; the last one repeats.
    """

    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.checks = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if text.startswith("Existing"):
                vectors.append([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            elif text.startswith("Which loop repeats"):
                score = self.scores[min(self.checks, len(self.scores) - 1)]
                self.checks += 1
                vectors.append([score, (1 - score**2) ** 0.5, 0.0, 0.0, 0.0, 0.0])
            else:
                vectors.extend(super().embed([text]))
        return vectors


def _flags(engine: Engine, question_id: int) -> list[QuestionSimilarityRow]:
    with Session(engine) as fresh:
        return list(
            fresh.scalars(
                select(QuestionSimilarityRow).where(
                    QuestionSimilarityRow.question_id == question_id
                )
            )
        )


def _dup_round(session: Session, env: SimpleNamespace, prompt: str) -> tuple[int, int]:
    existing = _question(
        session, env, env.while_loops, "medium", QuestionStatus.APPROVED, prompt=prompt
    )
    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    return existing.id, _queue(session, setup, [_target(env)]).id


def _mcq_client(env: SimpleNamespace) -> MetricJudgeClient:
    return MetricJudgeClient(
        draft=_mcq(env.while_loops.topic_id, env.while_loops.id), difficulty=Difficulty.MEDIUM
    )


def test_an_exact_duplicate_is_retried_quoting_it_then_kept_with_a_flag(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    """The fake draft never changes, so every attempt is a duplicate: the correction quotes
    the stored question, and the last attempt is kept with a flag rather than dropped."""
    draft = _mcq(env.while_loops.topic_id, env.while_loops.id)
    existing_id, round_id = _dup_round(
        session, env, "\n".join([draft.prompt, *draft.options]).upper()
    )
    client = _mcq_client(env)

    _run(engine, round_id, client)

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    retry_prompt = client.generation_calls[1]["prompt"]
    assert "Your question failed the check 'duplicate' (it is too similar to: WHICH LOOP" in (
        retry_prompt
    )
    (question,) = _round_questions(engine, round_id)
    assert [c.name for c in question.generation_attempts[0].failed_checks] == ["duplicate"]
    assert question.generation_attempts[-1].usable
    (flag,) = _flags(engine, question.id)
    assert (flag.similar_question_id, flag.score) == (existing_id, 1.0)
    done = _round(engine, round_id)
    assert (done.produced, done.dropped) == (1, 0)


def test_a_cosine_at_093_is_retried(session: Session, engine: Engine, env: SimpleNamespace) -> None:
    _, round_id = _dup_round(session, env, "Existing question about loops")
    client = _mcq_client(env)

    _run(engine, round_id, client, ScoredEmbedder([0.93, 0.10]))

    assert len(client.generation_calls) == 2
    assert "too similar to: Existing question about loops" in client.generation_calls[1]["prompt"]
    (question,) = _round_questions(engine, round_id)
    assert _flags(engine, question.id) == []


def test_a_cosine_at_080_is_kept_with_a_flag(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    existing_id, round_id = _dup_round(session, env, "Existing question about loops")
    client = _mcq_client(env)

    _run(engine, round_id, client, ScoredEmbedder([0.80]))

    assert len(client.generation_calls) == 1
    (question,) = _round_questions(engine, round_id)
    (flag,) = _flags(engine, question.id)
    assert flag.similar_question_id == existing_id
    assert flag.score == pytest.approx(0.80, abs=1e-5)
    assert flag.model == KeywordEmbedder.model


def test_a_duplicate_on_the_last_attempt_is_stored_with_a_flag(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    existing_id, round_id = _dup_round(session, env, "Existing question about loops")
    client = _mcq_client(env)

    _run(engine, round_id, client, ScoredEmbedder([0.95]))

    assert len(client.generation_calls) == MAX_GENERATION_ATTEMPTS
    (question,) = _round_questions(engine, round_id)
    assert question.status is QuestionStatus.VALIDATION_PASSED
    assert question.pedagogical_eval["metrics"]
    (flag,) = _flags(engine, question.id)
    assert flag.similar_question_id == existing_id
    assert flag.score == pytest.approx(0.95, abs=1e-5)
    assert _round(engine, round_id).dropped == 0


def _record_routing(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """The ``hold_for_review`` of every trust routing call."""
    import app.evaluation.trust as trust

    held: list[bool] = []
    route = trust.route_generated_question

    def recording(session: Session, row: QuestionRow, custom: Any = None, **kwargs: Any) -> str:
        held.append(kwargs.get("hold_for_review", False))
        return route(session, row, custom, **kwargs)

    monkeypatch.setattr(trust, "route_generated_question", recording)
    return held


def test_a_duplicate_kept_on_the_last_attempt_is_held_for_review(
    session: Session, engine: Engine, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trust routing must not auto-approve it: the professor has to see the flag."""
    held = _record_routing(monkeypatch)
    _, round_id = _dup_round(session, env, "Existing question about loops")

    _run(engine, round_id, _mcq_client(env), ScoredEmbedder([0.95]))

    assert held == [True]
    (question,) = _round_questions(engine, round_id)
    assert question.trust_provenance == "pending"


def test_a_question_that_only_resembles_one_is_routed_as_usual(
    session: Session, engine: Engine, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = _record_routing(monkeypatch)
    _, round_id = _dup_round(session, env, "Existing question about loops")

    _run(engine, round_id, _mcq_client(env), ScoredEmbedder([0.80]))

    assert held == [False]


# ------------------------------------------------------------------ examples (ADR-063 point 3)


class MarkerEmbedder:
    """Counts marker words. A target's query (section 0 + subtopic "While loops") holds only
    "while", so a question's cosine to the target is its share of "while"."""

    model = "marker-test-v1"
    VOCAB = ("alpha", "beta", "gamma", "while")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(t.lower().count(word)) for word in self.VOCAB] for t in texts]


class FailingEmbedder:
    model = "failing-test-v1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise LLMRequestError("embeddings are down")


MCQ = QuestionType.MULTIPLE_CHOICE


def _examples(session: Session, env: SimpleNamespace, embedder: object = None) -> RoundExamples:
    return rounds_module.accepted_examples(
        session,
        env.version.id,
        (env.while_loops.id, Difficulty.MEDIUM),
        MCQ,
        section_id=env.sections[0].id,
        embedder=embedder,  # type: ignore[arg-type]
    )


def _texts(examples: Sequence[ShownExample | str]) -> list[str]:
    return [item.text if isinstance(item, ShownExample) else item for item in examples]


def _approved(
    session: Session, env: SimpleNamespace, subtopic: SubtopicRow, prompt: str, **kwargs: Any
) -> QuestionRow:
    kwargs.setdefault("question_type", MCQ)
    return _professor_approved(
        session,
        _question(
            session, env, subtopic, "medium", QuestionStatus.APPROVED, prompt=prompt, **kwargs
        ),
    )


def _pending(session: Session, env: SimpleNamespace, prompt: str, **kwargs: Any) -> QuestionRow:
    kwargs.setdefault("status", QuestionStatus.GENERATED)
    return _question(session, env, env.while_loops, "medium", prompt=prompt, **kwargs)


@pytest.mark.parametrize("embedder", [None, MarkerEmbedder()], ids=["no-embedder", "embedder"])
def test_examples_are_only_of_the_targets_question_type(
    session: Session, env: SimpleNamespace, embedder: object
) -> None:
    """Regression: the cell lookup returned any type (73% of examples were another type)."""
    _approved(session, env, env.while_loops, "Choice alpha")
    _approved(session, env, env.while_loops, "Write code while", question_type=QuestionType.CODING)
    _approved(session, env, env.slicing, "Slice code", question_type=QuestionType.CODING)

    found = _examples(session, env, embedder)

    assert _texts(found.accepted) == ["Choice alpha"]
    assert _texts(found.style_only) == []
    # The other-type question of the cell is still something not to repeat.
    assert found.in_bank == ["Write code while"]


def test_an_empty_cell_falls_back_to_same_topic_then_similarity(
    session: Session, env: SimpleNamespace
) -> None:
    for_loops = SubtopicRow(topic_id=env.while_loops.topic_id, name="For loops", position=1)
    session.add(for_loops)
    session.commit()
    _approved(session, env, for_loops, "Same topic beta")
    _approved(session, env, for_loops, "Same topic while", question_type=QuestionType.CODING)
    _approved(session, env, env.slicing, "Other topic while while")
    _approved(session, env, env.slicing, "Other topic gamma")  # newest, but least similar

    found = _examples(session, env, MarkerEmbedder())

    assert _texts(found.accepted) == []
    assert _texts(found.style_only) == ["Same topic beta", "Other topic while while"]
    assert found.in_bank == []


def test_no_two_examples_are_near_identical(session: Session, env: SimpleNamespace) -> None:
    _approved(session, env, env.while_loops, "Choice beta")
    _approved(session, env, env.while_loops, "Choice while alpha")
    _approved(session, env, env.while_loops, "Choice while alpha again")  # cosine 1.0 to above

    found = _examples(session, env, MarkerEmbedder())

    assert _texts(found.accepted) == ["Choice while alpha again", "Choice beta"]
    first, second = (
        np.asarray(vector) / np.linalg.norm(vector)
        for vector in MarkerEmbedder().embed(_texts(found.accepted))
    )
    assert float(first @ second) <= EXAMPLE_PAIR_THRESHOLD
    # The skipped twin is in the cell, so it is shown as already in the bank.
    assert found.in_bank == ["Choice while alpha"]


def test_already_in_the_bank_is_the_three_nearest_of_the_cell(
    session: Session, env: SimpleNamespace
) -> None:
    """Approved or awaiting review, by cosine to the target (not by age); never rejected or
    another difficulty."""
    _pending(session, env, "while while gamma")  # 0.89
    _question(session, env, env.while_loops, "medium", QuestionStatus.APPROVED, prompt="while beta")
    _pending(session, env, "while while while", status=QuestionStatus.VALIDATION_PASSED)  # 1.0
    _pending(session, env, "gamma")  # newest, cosine 0
    _pending(session, env, "while", status=QuestionStatus.REJECTED)
    _question(session, env, env.while_loops, "easy", QuestionStatus.APPROVED, prompt="while")

    found = _examples(session, env, MarkerEmbedder())

    assert found.in_bank == ["while while while", "while while gamma", "while beta"]


@pytest.mark.parametrize("embedder", [None, FailingEmbedder()], ids=["none", "failing"])
def test_without_a_working_embedder_examples_and_the_bank_are_newest_first(
    session: Session, env: SimpleNamespace, embedder: object
) -> None:
    _approved(session, env, env.while_loops, "Old choice")
    _approved(session, env, env.while_loops, "New choice")
    _approved(session, env, env.while_loops, "Newest choice")
    _approved(session, env, env.slicing, "Elsewhere choice")
    for prompt in ("Pending one", "Pending two", "Pending three"):
        _pending(session, env, prompt)

    found = _examples(session, env, embedder)

    assert _texts(found.accepted) == ["Newest choice", "New choice"]
    assert found.in_bank == ["Pending three", "Pending two", "Pending one"]


def test_the_target_block_labels_style_only_examples_and_lists_the_bank() -> None:
    """Snapshot of the round target block with every kind of example."""
    subtopic = SubtopicRow(id=7, name="While loops", description="Using a while loop.")
    block = render_round_target(
        subtopic=subtopic,
        topic_name="Loops",
        style=STYLE_A,
        examples=RoundExamples(
            accepted=[ShownExample("What does a while loop do?", "  Good: one idea.  ")],
            style_only=["  Which slice gives 'el'?  ", ""],
            in_bank=["Which loop repeats while a condition holds?", "What ends a while loop?"],
            rejected=RejectedExample(
                "What is a loop?", "Too easy / trivial; asks for a definition"
            ),
        ),
    )
    assert block == "\n".join(
        [
            "--- target ---",
            "The question must assess this subtopic: [subtopic 7] While loops -- Using a while "
            "loop. (topic: Loops).",
            "Set topic_id to its topic and include 7 in subtopic_ids.",
            "",
            "Write it in this question style: Pick the right concept.",
            "What the student does: Pick the right concept: pick the one right option.",
            "How the answer is checked: Compares the chosen option with the key",
            "",
            "The professor accepted these questions for the same subtopic and difficulty. "
            "Match their level and quality; do not copy or paraphrase them.",
            "Example 1: What does a while loop do?",
            "  Professor's comment: Good: one idea.",
            "",
            "Style only: the professor accepted these questions of the same type for other "
            "subtopics or difficulties. Match their form only, not their content or level.",
            "Example 2 (style only): Which slice gives 'el'?",
            "",
            "The professor rejected a similar question because: Too easy / trivial; asks for "
            "a definition",
            "Do not repeat that mistake.",
            "Rejected: What is a loop?",
            "",
            "Already in the bank for this subtopic and difficulty -- assess something "
            "different from each of these:",
            "Existing 1: Which loop repeats while a condition holds?",
            "Existing 2: What ends a while loop?",
            "--- end target ---",
        ]
    )
    bare = render_round_target(subtopic=subtopic, topic_name="Loops", style=None)
    assert "Example" not in bare and "Existing" not in bare and "Rejected" not in bare
    assert "Avoid" not in bare


def test_the_target_block_lists_retry_lessons_before_the_bank() -> None:
    block = render_round_target(
        subtopic=SubtopicRow(id=7, name="While loops"),
        topic_name="Loops",
        style=None,
        examples=RoundExamples(
            in_bank=["What ends a while loop?"],
            avoid=["(medium) a reviewer rated it hard, but it must be medium"],
        ),
    )
    assert (
        "Earlier drafts for this subtopic failed these checks before a fixed version was "
        "approved. Avoid the same mistakes:\n"
        "Avoid 1: (medium) a reviewer rated it hard, but it must be medium\n"
        "\nAlready in the bank"
    ) in block


def test_a_round_prompt_carries_examples_and_the_bank(
    session: Session, engine: Engine, env: SimpleNamespace
) -> None:
    _approved(session, env, env.slicing, "Elsewhere: which slice?")
    _pending(session, env, "Pending: while?")
    setup = _setup(session, env, [(env.while_loops.id, "medium", 3)])
    round_id = _queue(session, setup, [_target(env)]).id
    client = _mcq_client(env)

    _run(engine, round_id, client)

    prompt = client.generation_calls[0]["prompt"]
    assert "Example 1 (style only): Elsewhere: which slice?" in prompt
    assert "Existing 1: Pending: while?" in prompt


def test_the_replay_script_reports_both_methods(session: Session, env: SimpleNamespace) -> None:
    """scripts/replay_retrieval.py with a fake embedder. Approved in order: a coding question
    of the cell, an MCQ elsewhere, an MCQ of the cell. For the last, the old lookup shows the
    coding question; the implemented one shows the MCQ from elsewhere."""
    from scripts.replay_retrieval import replay

    for subtopic, prompt, kind in (
        (env.while_loops, "Write a while loop", QuestionType.CODING),
        (env.slicing, "Which slice?", MCQ),
        (env.while_loops, "Which loop repeats while?", MCQ),
    ):
        row = _approved(session, env, subtopic, prompt, question_type=kind)
        row.content = {"sources": [{"section_id": env.sections[0].id}]}
        session.add(ProfessorReviewRow(question_id=row.id, decision=ReviewDecision.APPROVE))
        session.commit()

    report = replay(session, MarkerEmbedder())

    # The first target has nothing approved before it; the second finds nothing either way.
    assert {
        method: (r["targets"], r["coverage"], r["same_type"]) for method, r in report.items()
    } == {
        "DB": (2, 0.5, 0.0),
        "REC": (2, 0.5, 1.0),
    }
    assert report["REC"]["same_subtopic"] == 0.0
