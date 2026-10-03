"""The style library and the setup suggester (docs/QUESTION_SETUP_PLAN.md, agent A)."""

from __future__ import annotations

import ast
import contextlib
import io
from typing import Any

import pytest
from llm_fakes import as_live
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.coverage.schema import MIN_QUESTIONS_PER_CELL
from app.domain.enums import CurriculumStatus, Difficulty, QuestionType
from app.errors import DomainRuleError, FeatureNotAvailableError, NotFoundError
from app.persistence.models import CourseRow, CurriculumVersionRow, SubtopicRow, TopicRow
from app.styles import MAX_CELL_TARGET, MIN_CELL_TARGET, get_library, suggest_setup
from app.styles.python import PYTHON_STYLES

PYTHON = "intro_python"


class FakeSuggester:
    """Answers the suggester's one structured call with a canned payload, and records it."""

    description = "fake/suggester"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def complete_structured(
        self, *, system: str, prompt: str, response_model: type[BaseModel]
    ) -> BaseModel:
        self.calls.append({"system": system, "prompt": prompt})
        # As the live client returns it: an instance of instructor's subclass of the model.
        return as_live(response_model.model_validate(self.payload))


def make_taxonomy(
    session: Session,
    *,
    status: CurriculumStatus = CurriculumStatus.APPROVED,
    course: CourseRow | None = None,
) -> tuple[CurriculumVersionRow, list[SubtopicRow]]:
    version = CurriculumVersionRow(label="Intro", status=status)
    if course is not None:
        session.add(course)
        session.flush()
        version.course_id = course.id
    loops = TopicRow(
        name="Loops",
        subtopics=[SubtopicRow(name="while loops", position=0), SubtopicRow(name="for loops")],
    )
    files = TopicRow(name="File I/O", subtopics=[SubtopicRow(name="Reading text files")])
    version.topics.extend([loops, files])
    session.add(version)
    session.commit()
    return version, [*loops.subtopics, *files.subtopics]


# ------------------------------------------------------------------ library


def test_python_library_is_valid() -> None:
    styles = get_library(PYTHON)
    assert 8 <= len(styles) <= 12
    ids = [style.id for style in styles]
    assert len(ids) == len(set(ids))
    assert all(style_id.startswith("py.") for style_id in ids)
    for style in styles:
        assert style.subject == PYTHON
        assert len(style.examples) == 2
        assert style.name and style.summary and style.checked_by and style.applies_to
    # Every Intro Python question type has a style, and every difficulty has several.
    assert {style.question_type for style in styles} == {
        QuestionType(type_id)
        for type_id in (
            "multiple_choice",
            "true_false",
            "parsons",
            "output_prediction",
            "code_completion",
            "debugging",
            "coding",
        )
    }
    for difficulty in Difficulty:
        assert sum(difficulty in style.difficulty_range for style in styles) >= 3


def test_unknown_subject_has_no_library() -> None:
    assert get_library("physics") == []
    assert get_library("custom:7") == []


def test_get_library_returns_a_copy() -> None:
    get_library(PYTHON).clear()
    assert len(get_library(PYTHON)) == len(PYTHON_STYLES)


def _run(code: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, "<example>", "exec"), {})
    return out.getvalue().strip()


@pytest.mark.parametrize(
    "example",
    [
        pytest.param(example, id=f"{style.id}-{n}")
        for style in PYTHON_STYLES
        if style.question_type is QuestionType.OUTPUT_PREDICTION
        for n, example in enumerate(style.examples)
    ],
)
def test_output_examples_print_their_answer(example: Any) -> None:
    assert _run(example.code) == example.answer


def test_choice_examples_have_exactly_one_correct_option() -> None:
    for style in PYTHON_STYLES:
        if style.question_type in (QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
            for example in style.examples:
                assert sum(option.correct for option in example.options) == 1, style.id


def test_code_examples_parse() -> None:
    for style in PYTHON_STYLES:
        for example in style.examples:
            if example.lines:
                ast.parse("\n".join(example.lines))
            if example.code and "____" not in example.code:
                ast.parse(example.code)


def test_debugging_examples_are_really_broken() -> None:
    """The two fix-one-bug examples misbehave exactly as their prompts say."""
    average = _define(PYTHON_STYLES, "py.fix_one_bug", 0, "average")
    assert average([2, 3]) == 1.5
    find_index = _define(PYTHON_STYLES, "py.edge_case_bug", 0, "find_index")
    assert find_index([1, 2, 3], 3) == -1  # gives up after the first item
    fact = _define(PYTHON_STYLES, "py.edge_case_bug", 1, "fact")
    with pytest.raises(RecursionError):
        fact(0)


def _define(styles: list[Any], style_id: str, index: int, name: str) -> Any:
    (style,) = [s for s in styles if s.id == style_id]
    namespace: dict[str, Any] = {}
    exec(style.examples[index].code, namespace)
    return namespace[name]


# ------------------------------------------------------------------ suggester


def _entry(subtopic: SubtopicRow, styles: list[str], **targets: int | None) -> dict[str, Any]:
    return {"subtopic_id": subtopic.id, "style_ids": styles, "reason": "fits", **targets}


def test_suggestion_keeps_valid_styles_and_targets(session: Session) -> None:
    version, (while_loops, for_loops, reading) = make_taxonomy(session)
    fake = FakeSuggester(
        {
            "subtopics": [
                _entry(
                    while_loops,
                    ["py.trace_steps", "py.predict_output", "py.subtle_output"],
                    easy=2,
                    medium=4,
                    hard=5,
                ),
                _entry(for_loops, ["py.concept_check", "py.write_function"], easy=3, medium=3),
                _entry(reading, ["py.misconception", "py.concept_check"]),
            ]
        }
    )

    result = suggest_setup(session, version.id, client=fake)

    assert len(fake.calls) == 1
    prompt = fake.calls[0]["prompt"]
    assert "py.trace_steps" in prompt and str(while_loops.id) in prompt
    assert result.subject == PYTHON
    by_id = {s.subtopic_id: s for s in result.subtopics}
    assert by_id[while_loops.id].style_ids == [
        "py.trace_steps",
        "py.predict_output",
        "py.subtle_output",
    ]
    assert by_id[while_loops.id].reason == "fits"
    targets = {(c.subtopic_id, c.difficulty): c.target for c in result.cell_targets}
    assert len(targets) == 3 * 3
    assert targets[(while_loops.id, Difficulty.EASY)] == 2
    assert targets[(while_loops.id, Difficulty.HARD)] == 5
    # Missing targets default to the coverage minimum.
    assert targets[(for_loops.id, Difficulty.HARD)] == MIN_QUESTIONS_PER_CELL
    assert targets[(reading.id, Difficulty.MEDIUM)] == MIN_QUESTIONS_PER_CELL


def test_suggestion_drops_unknown_styles_clamps_and_fills_gaps(session: Session) -> None:
    version, (while_loops, for_loops, reading) = make_taxonomy(session)
    fake = FakeSuggester(
        {
            "subtopics": [
                _entry(
                    while_loops,
                    ["py.made_up", "py.predict_output", "py.predict_output"],
                    easy=0,
                    medium=99,
                    hard=-3,
                ),
                _entry(for_loops, ["nope", "also.nope"], easy=4),
                # ``reading`` is missing; an unknown subtopic id is ignored.
                {"subtopic_id": 999_999, "style_ids": ["py.concept_check"], "reason": "x"},
            ]
        }
    )

    result = suggest_setup(session, version.id, client=fake)

    by_id = {s.subtopic_id: s for s in result.subtopics}
    assert set(by_id) == {while_loops.id, for_loops.id, reading.id}
    library = {style.id: style for style in get_library(PYTHON)}
    for suggestion in result.subtopics:
        assert suggestion.style_ids, suggestion
        assert set(suggestion.style_ids) <= set(library)
        assert len(suggestion.style_ids) == len(set(suggestion.style_ids))
        for difficulty in Difficulty:
            assert any(
                difficulty in library[style_id].difficulty_range
                for style_id in suggestion.style_ids
            ), (suggestion.subtopic_id, difficulty)

    # The model's valid pick stays first; easy-only, so medium and hard styles were added.
    assert by_id[while_loops.id].style_ids[0] == "py.predict_output"
    assert "py.made_up" not in by_id[while_loops.id].style_ids
    # No valid pick at all: chosen by fit, and said so.
    assert by_id[for_loops.id].reason != "fits"
    assert by_id[reading.id].reason == by_id[for_loops.id].reason

    targets = {(c.subtopic_id, c.difficulty): c.target for c in result.cell_targets}
    assert targets[(while_loops.id, Difficulty.EASY)] == MIN_CELL_TARGET
    assert targets[(while_loops.id, Difficulty.MEDIUM)] == MAX_CELL_TARGET
    assert targets[(while_loops.id, Difficulty.HARD)] == MIN_CELL_TARGET
    assert targets[(for_loops.id, Difficulty.EASY)] == 4
    assert all(MIN_CELL_TARGET <= t <= MAX_CELL_TARGET for t in targets.values())


def test_fallback_prefers_styles_whose_hints_match(session: Session) -> None:
    version, (while_loops, *_rest) = make_taxonomy(session)
    result = suggest_setup(session, version.id, client=FakeSuggester({"subtopics": []}))
    by_id = {s.subtopic_id: s for s in result.subtopics}
    # "while loops" is a hint of the trace style, not of the first library style.
    assert by_id[while_loops.id].style_ids[0] == "py.trace_steps"


def test_suggestion_respects_the_course_question_types(session: Session) -> None:
    course = CourseRow(
        name="CS 110", subject=PYTHON, question_types=["multiple_choice", "output_prediction"]
    )
    version, _subtopics = make_taxonomy(session, course=course)
    fake = FakeSuggester({"subtopics": []})

    result = suggest_setup(session, version.id, client=fake)

    assert "py.write_function" not in fake.calls[0]["prompt"]
    allowed = {QuestionType.MULTIPLE_CHOICE, QuestionType.OUTPUT_PREDICTION}
    library = {style.id: style for style in get_library(PYTHON)}
    for suggestion in result.subtopics:
        assert {library[s].question_type for s in suggestion.style_ids} <= allowed


def test_suggestion_refuses_unapproved_missing_and_unsupported(session: Session) -> None:
    fake = FakeSuggester({"subtopics": []})
    proposed, _ = make_taxonomy(session, status=CurriculumStatus.PROPOSED)
    with pytest.raises(DomainRuleError):
        suggest_setup(session, proposed.id, client=fake)
    with pytest.raises(NotFoundError):
        suggest_setup(session, 999_999, client=fake)
    physics, _ = make_taxonomy(session, course=CourseRow(name="Physics", subject="physics"))
    with pytest.raises(FeatureNotAvailableError):
        suggest_setup(session, physics.id, client=fake)
    assert fake.calls == []
