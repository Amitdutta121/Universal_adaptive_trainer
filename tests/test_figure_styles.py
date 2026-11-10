"""fig2: styles ask for a figure; diagram and chart questions are generated (ADR-080).

docs/FIGURE_QUESTIONS_MILESTONES.md, fig2. The style drafter and the generator are driven by a
fake model: the tests prove what they are told, what they accept and what they store, for two
unrelated subjects, and that a style without a figure asks for exactly what it did before.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import book_documents as docs
import pytest
from llm_fakes import MetricJudgeClient, SequencedDraftClient
from pydantic import BaseModel
from sqlalchemy.orm import Session
from test_figures_universal import SUBJECT_WORDS

from app.assessment.catalog import SUBJECTS
from app.domain.enums import CurriculumStatus, Difficulty, QuestionType
from app.generation import GenerationService
from app.generation.base import BaseQuestionGenerator
from app.generation.computed import STDLIB_MODULES, program_instructions
from app.generation.prompts import FIGURE_KIND_RULES, FIGURE_RULES, figure_rules
from app.generation.schemas import MultipleChoiceDraft, response_model_for, with_figure
from app.generation.spec import build_question_spec
from app.persistence.models import CourseRow, CurriculumVersionRow, SubtopicRow, TopicRow
from app.styles import QuestionStyle
from app.styles.drafting import FIGURE_SYSTEM, SYSTEM, StyleDraft, draft_style
from app.subjects import profile_for

DIAGRAM = {
    "kind": "diagram",
    "source": 'flowchart LR\n  A["Stage A"] -->|signal| B["Stage B"]\n  B --> C["Stage C"]',
    "alt": "Stage A leads to Stage B on a signal, and Stage B leads to Stage C.",
    "caption": "Three stages",
}
CHART = {
    "kind": "chart",
    "chart": {
        "type": "bar",
        "data": {
            "labels": ["2019", "2020", "2021"],
            "datasets": [{"label": "Units", "data": [4, 9, 6]}],
        },
        "x_title": "Year",
        "y_title": "Units",
    },
    "alt": "Units per year: 2019 is 4, 2020 is 9, 2021 is 6.",
    "caption": "Units per year",
}


# --- helpers ---------------------------------------------------------------------------------


def figure_course(
    session: Session, *, subject: str, name: str, question_types: list[str]
) -> SimpleNamespace:
    """A course of ``subject`` with one book chunk and an approved one-subtopic taxonomy."""
    course = CourseRow(name=name, subject=subject, question_types=question_types)
    session.add(course)
    session.flush()
    book = docs.chunked_book(
        session,
        {
            "schema_version": "1",
            "title": f"{name} notes",
            "chapters": [{"sections": [{"text": "The material moves through three stages."}]}],
        },
        course_id=course.id,
    )
    version = CurriculumVersionRow(
        label="v1",
        course_id=course.id,
        status=CurriculumStatus.APPROVED,
        approved_at=datetime.now(UTC),
        source_book_ids=[book.id],
    )
    session.add(version)
    session.flush()
    topic = TopicRow(curriculum_version_id=version.id, name="Stages", position=0)
    session.add(topic)
    session.flush()
    subtopic = SubtopicRow(topic_id=topic.id, name="Order of stages", position=0)
    session.add(subtopic)
    session.commit()
    return SimpleNamespace(
        course=course,
        version=version,
        topic=topic,
        subtopic=subtopic,
        chunk_id=book.chunks[0].id,
        profile=profile_for(course),
    )


def figure_style(
    style_id: str,
    figure: str,
    *,
    subject: str,
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    example_figure: dict | None = None,
) -> QuestionStyle:
    example: dict[str, Any] = {"prompt": "Which stage comes after Stage A?", "answer": "Stage B"}
    if example_figure is not None:
        example["figure"] = example_figure
    return QuestionStyle(
        id=style_id,
        subject=subject,
        name="Read the figure",
        summary="Read the figure and answer about what it shows.",
        question_type=question_type,
        difficulty_range=[Difficulty.EASY, Difficulty.MEDIUM, Difficulty.HARD],
        checked_by="Compares the answer with the key",
        figure=figure,  # type: ignore[arg-type]
        examples=(example, example),
    )


def round_spec(
    session: Session,
    env: SimpleNamespace,
    style: QuestionStyle,
    *,
    difficulty: Difficulty = Difficulty.MEDIUM,
) -> Any:
    return build_question_spec(
        session,
        curriculum_version_id=env.version.id,
        question_type=style.question_type,
        difficulty=difficulty,
        source_chunk_ids=[env.chunk_id],
        target_subtopic_id=env.subtopic.id,
        style_id=style.id,
    )


@pytest.fixture
def library(monkeypatch: pytest.MonkeyPatch) -> list[QuestionStyle]:
    """The styles every course sees, set per test."""
    import app.styles.library

    styles: list[QuestionStyle] = []
    monkeypatch.setattr(app.styles.library, "get_library", lambda subject: list(styles))
    return styles


# --- universality: the figure prompt text names no subject -----------------------------------


def _subject_words_in(text: str) -> list[str]:
    banned = {preset.id for preset in SUBJECTS if preset.id != "custom"} | set(SUBJECT_WORDS)
    lowered = text.lower()
    return sorted(w for w in banned if re.search(rf"\b{re.escape(w.lower())}\b", lowered))


def test_the_figure_prompt_text_names_no_subject() -> None:
    from app.course_design.design import STYLE_SYSTEM

    figure_lines = [line for line in STYLE_SYSTEM.splitlines() if "figure" in line.lower()]
    # The import allowlist names standard modules (``statistics``), not a subject.
    modules = ", ".join(sorted(STDLIB_MODULES - {"__future__"}))
    programs = [
        program_instructions(question_type).replace(modules, "")
        for question_type in (
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.NUMERIC_RESPONSE,
            QuestionType.TRUE_FALSE,
        )
    ]
    texts = [
        FIGURE_SYSTEM,
        *FIGURE_RULES,
        *(rule for rules in FIGURE_KIND_RULES.values() for rule in rules),
        *("\n".join(figure_rules(kind)) for kind in ("diagram", "chart", "computed")),
        *figure_lines,
        *programs,
    ]
    assert figure_lines and all(modules not in text for text in programs)
    assert {text: _subject_words_in(text) for text in texts if _subject_words_in(text)} == {}


# --- the style drafter -----------------------------------------------------------------------


class DrafterClient:
    """Answers the style drafter with a scripted draft and records what it was told."""

    description = "fake/drafter"

    def __init__(self, draft: StyleDraft) -> None:
        self.draft = draft
        self.calls: list[dict[str, str]] = []

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel], **_: Any
    ) -> BaseModel:
        assert response_model is StyleDraft
        self.calls.append({"system": system, "prompt": prompt})
        return self.draft


def _mcq_example(prompt: str, figure: dict | None) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "options": [{"text": "Stage B", "correct": True}, {"text": "Stage C"}],
        "answer": "Stage B follows Stage A.",
        **({"figure": figure} if figure else {}),
    }


def _draft(slug: str, figure: str, example_figure: dict | None, prompt: str) -> StyleDraft:
    return StyleDraft.model_validate(
        {
            "slug": slug,
            "name": "Read the figure",
            "summary": "Read the figure and pick the right option.",
            "question_type": "multiple_choice",
            "difficulty_range": ["easy", "medium"],
            "checked_by": "Compares the chosen option with the key",
            "figure": figure,
            "examples": [_mcq_example(prompt, example_figure)] * 2,
        }
    )


@pytest.mark.parametrize(
    ("subject", "name", "figure", "example_figure", "material"),
    [
        ("biology", "Cell biology", "diagram", DIAGRAM, "the stages of a cycle"),
        ("custom", "Market data", "chart", CHART, "a small yearly dataset"),
    ],
)
def test_the_drafter_makes_a_figure_style_for_structure_or_data_in_any_subject(
    session: Session,
    library: list[QuestionStyle],
    subject: str,
    name: str,
    figure: str,
    example_figure: dict,
    material: str,
) -> None:
    env = figure_course(
        session, subject=subject, name=name, question_types=["multiple_choice", "true_false"]
    )
    client = DrafterClient(_draft("read_it", figure, example_figure, "Which value is largest?"))

    result = draft_style(session, env.profile, client, f"Ask students to read {material}.")

    assert result.problems == []
    assert result.style is not None and result.style.figure == figure
    assert result.style.examples[0].figure is not None
    assert result.style.examples[0].figure.kind == figure
    (call,) = client.calls
    # The same subject-neutral rules for every course, and the kinds it may choose from.
    assert call["system"] == SYSTEM and FIGURE_SYSTEM in call["system"]
    assert "Figure kinds: none; diagram (" in call["prompt"] and "chart (" in call["prompt"]
    assert "computed (" in call["prompt"]


def test_the_drafter_keeps_none_for_recall_and_refuses_a_figure_it_was_not_asked_for(
    session: Session, library: list[QuestionStyle]
) -> None:
    env = figure_course(
        session, subject="biology", name="Cell biology", question_types=["multiple_choice"]
    )
    plain = DrafterClient(_draft("define_it", "none", None, "Which term names the cell's store?"))

    result = draft_style(session, env.profile, plain, "Ask students to recall a definition.")

    assert result.problems == [] and result.style is not None
    assert result.style.figure == "none"
    assert result.style.examples[0].figure is None
    assert "A style that asks to recall a definition, a fact or a term keeps\n`none`" in SYSTEM

    mismatched = DrafterClient(_draft("define_it", "none", DIAGRAM, "Which term is this?"))
    refused = draft_style(session, env.profile, mismatched, "Ask students to recall a term.")
    assert any("examples carry none" in problem for problem in refused.problems)
    assert len(mismatched.calls) == 2  # one repair, naming the problem
    assert "examples carry none" in mismatched.calls[1]["prompt"]


def test_a_diagram_style_example_must_be_drawable(
    session: Session, library: list[QuestionStyle]
) -> None:
    env = figure_course(
        session, subject="custom", name="Systems", question_types=["multiple_choice"]
    )
    broken = {**DIAGRAM, "source": "flowchart LR\n  A --> B\n  click A callback"}
    client = DrafterClient(_draft("read_it", "diagram", broken, "Which stage follows A?"))

    result = draft_style(session, env.profile, client, "Ask students to read a process.")

    assert result.problems and all("figure" in problem for problem in result.problems)


# --- generation of diagram and chart questions ------------------------------------------------


def _figure_draft(env: SimpleNamespace, kind: str, figure: dict) -> MultipleChoiceDraft:
    model = with_figure(MultipleChoiceDraft, kind)
    return model.model_validate(  # type: ignore[return-value]
        {
            "topic_id": env.topic.id,
            "subtopic_ids": [env.subtopic.id],
            "prompt": "Which stage comes right after Stage A in the figure?",
            "options": ["Stage B", "Stage C", "Stage A", "None of them"],
            "correct_option_index": 0,
            "explanation": "The arrow from Stage A points to Stage B.",
            "figure": figure,
        }
    )


@pytest.mark.parametrize(
    ("subject", "kind", "figure"),
    [("biology", "diagram", DIAGRAM), ("custom", "chart", CHART)],
)
def test_a_generated_figure_question_passes_its_types_checks_and_keeps_the_figure(
    session: Session,
    library: list[QuestionStyle],
    subject: str,
    kind: str,
    figure: dict,
) -> None:
    env = figure_course(session, subject=subject, name="Course", question_types=["multiple_choice"])
    style = figure_style(f"c{env.course.id}.read_{kind}", kind, subject=env.profile.storage_key)
    library.append(style)
    client = MetricJudgeClient(draft=_figure_draft(env, kind, figure), difficulty=Difficulty.MEDIUM)

    row = GenerationService(session, client=client).generate_round_question(
        round_spec(session, env, style), version=env.version, round_id=None
    )

    assert row is not None
    assert row.content["figure"] == figure
    assert row.validation_report.passed
    checks = {check.name: check.passed for check in row.validation_report.checks}
    assert checks["figure_drawable"] is True
    (call,) = client.generation_calls
    assert call["model"] is response_model_for(QuestionType.MULTIPLE_CHOICE, style)
    assert "figure" in call["model"].model_fields
    assert "\n".join(figure_rules(kind)) in call["prompt"]


def test_a_figure_that_cannot_be_drawn_is_sent_back_for_repair(
    session: Session, library: list[QuestionStyle]
) -> None:
    env = figure_course(
        session, subject="custom", name="Course", question_types=["multiple_choice"]
    )
    style = figure_style(
        f"c{env.course.id}.read_diagram", "diagram", subject=env.profile.storage_key
    )
    library.append(style)
    broken = _figure_draft(env, "diagram", {**DIAGRAM, "source": "flowchart LR\n  click A x"})
    client = SequencedDraftClient(
        drafts=[broken, _figure_draft(env, "diagram", DIAGRAM)], difficulty=Difficulty.MEDIUM
    )

    row = GenerationService(session, client=client).generate_round_question(
        round_spec(session, env, style), version=env.version, round_id=None
    )

    assert row is not None and row.content["figure"] == DIAGRAM
    first, second = row.generation_attempts
    assert [check.name for check in first.failed_checks] == ["figure_drawable"]
    assert second.usable
    assert "figure check" in client.generation_calls[1]["prompt"]


def test_a_style_without_a_figure_asks_for_the_plain_draft(
    session: Session, library: list[QuestionStyle]
) -> None:
    env = figure_course(
        session, subject="custom", name="Course", question_types=["multiple_choice"]
    )
    style = figure_style(f"c{env.course.id}.plain", "none", subject=env.profile.storage_key)
    library.append(style)

    prepared = BaseQuestionGenerator(session=session).prepare(
        round_spec(session, env, style), version=env.version
    )

    assert response_model_for(QuestionType.MULTIPLE_CHOICE, style) is MultipleChoiceDraft
    assert "shows the student a" not in prepared.prompt
    assert all(rule not in prepared.prompt for rule in FIGURE_RULES)
    assert prepared.style == style
    assert prepared.sources == [
        {"chunk_id": env.chunk_id, "citation": prepared.sources[0]["citation"]}
    ]


def test_generate_one_refuses_a_computed_style(
    session: Session, library: list[QuestionStyle]
) -> None:
    from app.errors import DomainRuleError

    env = figure_course(
        session, subject="custom", name="Course", question_types=["multiple_choice"]
    )
    style = figure_style(f"c{env.course.id}.drawn", "computed", subject=env.profile.storage_key)
    library.append(style)

    with pytest.raises(DomainRuleError, match="computed-figure style"):
        BaseQuestionGenerator(session=session, client=MetricJudgeClient()).generate_one(
            round_spec(session, env, style), version=env.version
        )
