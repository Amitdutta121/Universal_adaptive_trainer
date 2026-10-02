"""Numeric response (T1): generated, validated, served and scored through ``quantity.units``."""

from __future__ import annotations

from types import SimpleNamespace

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adaptive.scoring import score_answer
from app.assessment.catalog import TYPES_BY_ID, default_types_for, is_offerable
from app.assessment.specs import Unmarkable, plan_for
from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionKind, QuestionStatus, QuestionType
from app.domain.questions import Question
from app.generation.prompts import base_type_instruction
from app.generation.schemas import build_content, response_model_for, scoring_kind_for
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository
from app.question_types import get_type, implemented_types
from app.question_types.numeric_response import NumericResponseDraft
from app.validation import get_question_validator
from app.validation.runner import LocalCodeRunner
from app.web.routes.api.schemas import ServedQuestionOut
from graders import get_grader

TAXONOMY = (
    b'{"schema_version":"1","label":"Physics","topics":['
    b'{"name":"Kinematics","subtopics":[{"name":"Free fall"},{"name":"Projectiles"}]}]}'
)

PROMPT = "A ball is dropped from rest on Earth. What is its acceleration while it falls?"


def _draft(
    topic_id: int = 1, subtopic_ids: list[int] | None = None, **overrides
) -> NumericResponseDraft:
    fields = {
        "topic_id": topic_id,
        "subtopic_ids": subtopic_ids or [1],
        "prompt": PROMPT,
        "value": 9.81,
        "unit": "m/s^2",
        "relative_tolerance": 0.01,
        "explanation": "Near Earth's surface every falling body accelerates at g.",
    }
    fields.update(overrides)
    return NumericResponseDraft(**fields)


def _question(draft: NumericResponseDraft | None = None, **content_overrides) -> Question:
    content = build_content(draft or _draft())
    content.update(content_overrides)
    return Question(
        id=1,
        prompt=content["prompt"],
        question_type=QuestionType.NUMERIC_RESPONSE,
        kind=QuestionKind.DISCRETE,
        content=content,
    )


# --- the module is registered --------------------------------------------------------------


def test_the_type_is_built_and_discrete() -> None:
    assert QuestionType.NUMERIC_RESPONSE in implemented_types()
    assert response_model_for(QuestionType.NUMERIC_RESPONSE) is NumericResponseDraft
    assert scoring_kind_for(QuestionType.NUMERIC_RESPONSE) is QuestionKind.DISCRETE


def test_the_shipped_instruction_is_subject_neutral() -> None:
    instruction = base_type_instruction(QuestionType.NUMERIC_RESPONSE)
    assert instruction == get_type(QuestionType.NUMERIC_RESPONSE).instruction
    lowered = instruction.lower()
    for word in ("python", "code", "program", "tests", "function", "print"):
        assert word not in lowered


# --- the draft schema ------------------------------------------------------------------------


def test_a_draft_needs_a_usable_tolerance() -> None:
    with pytest.raises(ValidationError, match="tolerance"):
        _draft(relative_tolerance=0, absolute_tolerance=None)
    with pytest.raises(ValidationError, match="absolute_tolerance"):
        _draft(value=0, relative_tolerance=0.01)
    assert _draft(value=0, absolute_tolerance=0.001).absolute_tolerance == 0.001
    with pytest.raises(ValidationError):
        _draft(relative_tolerance=-0.1)


def test_a_draft_rejects_non_finite_values_and_empty_accepted_units() -> None:
    with pytest.raises(ValidationError):
        _draft(value=float("nan"))
    with pytest.raises(ValidationError, match="accepted_units"):
        _draft(accepted_units=[])
    with pytest.raises(ValidationError):
        _draft(sig_figs=0)
    assert _draft(unit="  m/s^2 ").unit == "m/s^2"


def test_columns_carry_the_answer_as_reference() -> None:
    columns = get_type(QuestionType.NUMERIC_RESPONSE).columns_from_draft(_draft())
    assert columns.prompt == PROMPT
    assert columns.reference_solution == "9.81 m/s^2"
    assert columns.tests is None
    integral = get_type(QuestionType.NUMERIC_RESPONSE).columns_from_draft(_draft(value=20))
    assert integral.reference_solution == "20 m/s^2"


# --- acceptance 1: a fake-LLM draft becomes a stored, validated question --------------------


def test_a_generated_draft_is_stored_and_passes_validation(session: Session, settings) -> None:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.think_python())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json", data=TAXONOMY
    )
    session.commit()
    topic = version.topics[0]
    subtopic = topic.subtopics[0]
    section_id = book.chapters[0].sections[0].id
    client = MetricJudgeClient(draft=_draft(topic.id, [subtopic.id]))

    rows = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.NUMERIC_RESPONSE,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )

    (row,) = rows
    assert QuestionRepository(session).count() == 1
    assert client.generation_calls[0]["model"] is NumericResponseDraft
    assert (
        get_type(QuestionType.NUMERIC_RESPONSE).instruction in client.generation_calls[0]["prompt"]
    )
    assert row.question_type is QuestionType.NUMERIC_RESPONSE
    assert row.kind is QuestionKind.DISCRETE
    assert row.reference_solution == "9.81 m/s^2"
    assert row.content["value"] == 9.81 and row.content["unit"] == "m/s^2"
    report = row.validation_report
    failed = [check.name for check in report.checks if not check.passed]
    assert failed == []
    assert report.passed
    assert row.status is QuestionStatus.VALIDATION_PASSED
    names = {check.name for check in report.checks}
    assert {"numeric_value_not_in_prompt", "numeric_explanation_present"} <= names

    # The stored row scores like any other: what was stored is what is marked.
    stored = Question.model_validate(row)
    assert score_answer(stored, "9.81 m/s^2").score == 100


def test_validation_fails_a_prompt_that_states_the_answer(session: Session) -> None:
    question = _question(_draft(prompt="Show that g is 9.81 m/s^2 near the surface."))
    report = get_question_validator(session).validate(question)
    check = next(c for c in report.checks if c.name == "numeric_value_not_in_prompt")
    assert not check.passed
    assert "9.81" in (check.evidence or "")


def test_authoring_checks_pass_a_sound_question_and_ignore_other_numbers() -> None:
    module = get_type(QuestionType.NUMERIC_RESPONSE)
    content = build_content(
        _draft(prompt="A ball falls from rest for 2 s. Its speed, in m/s?", value=19.62)
    )
    assert all(check.passed for check in module.authoring_checks(content, LocalCodeRunner()))
    content["explanation"] = " "
    failed = [c.name for c in module.authoring_checks(content, LocalCodeRunner()) if not c.passed]
    assert failed == ["numeric_explanation_present"]


# --- acceptance 2: scoring through quantity.units -------------------------------------------


@pytest.mark.parametrize("answer", ["9.81 m/s^2", "981 cm/s^2", "9.8m/s**2", "9.81 m/s²"])
def test_equivalent_answers_score_full_marks(answer: str) -> None:
    assert score_answer(_question(), answer).score == 100


def test_a_wrong_dimension_scores_zero_with_a_format_message() -> None:
    question = _question()
    scored = score_answer(question, "9.81 kg")
    assert scored.score == 0

    # The grader states why: the answer is not in a form the question accepts.
    plan = plan_for(question.question_type, question.content)
    result = get_grader(plan.capability).grade(plan.spec, plan.rewrite_answer("9.81 kg"))
    assert result.score == 0
    assert result.format_error and "doesn't match" in result.format_error


def test_a_wrong_value_scores_zero() -> None:
    scored = score_answer(_question(), "12 m/s^2")
    assert scored.score == 0
    assert scored.detail == "Near Earth's surface every falling body accelerates at g."


def test_tolerance_accepted_units_and_sig_figs_reach_the_grader() -> None:
    assert score_answer(_question(), "9.9 m/s^2").score == 100  # within 1%
    assert score_answer(_question(), "10 m/s^2").score == 0
    absolute = _question(_draft(relative_tolerance=None, absolute_tolerance=0.5))
    assert score_answer(absolute, "10.2 m/s^2").score == 100
    only_si = _question(_draft(accepted_units=["m/s^2"]))
    assert score_answer(only_si, "981 cm/s^2").score == 0
    assert score_answer(only_si, "9.81 m/s^2").score == 100
    three = _question(_draft(sig_figs=3))
    assert score_answer(three, "9.8 m/s^2").score == 0
    assert score_answer(three, "9.81 m/s^2").score == 100


def test_a_pure_number_needs_no_unit() -> None:
    count = _question(_draft(prompt="How many recessive offspring?", value=75, unit=""))
    assert score_answer(count, "75").score == 100


def test_a_stored_question_without_a_value_is_unmarkable() -> None:
    module = get_type(QuestionType.NUMERIC_RESPONSE)
    with pytest.raises(Unmarkable):
        module.grading_plan({"unit": "m"}, None)
    with pytest.raises(Unmarkable):
        module.grading_plan({"value": True, "unit": "m"}, None)
    with pytest.raises(Unmarkable):
        module.grading_plan({"value": 1.0}, None)


def test_the_grading_plan_is_a_valid_quantity_spec() -> None:
    plan = plan_for(QuestionType.NUMERIC_RESPONSE, build_content(_draft()))
    assert plan.capability == "quantity.units"
    assert get_grader(plan.capability).check_spec(plan.spec) == []


# --- acceptance 3: the catalog offers it, and a Physics course can choose it ----------------


def test_the_catalog_offers_it_for_physics() -> None:
    assert TYPES_BY_ID["numeric_response"].implemented
    assert is_offerable("numeric_response")
    assert "numeric_response" in default_types_for("physics")


def test_a_physics_course_can_be_created_with_it(client: TestClient) -> None:
    response = client.post(
        "/api/courses",
        json={
            "name": "Physics 101",
            "subject": "physics",
            "question_types": ["multiple_choice", "numeric_response"],
        },
    )
    assert response.status_code == 201, response.text
    course = response.json()
    assert course["question_types"] == ["multiple_choice", "numeric_response"]
    assert "quantity.units" in course["capabilities"]


# --- acceptance 4: a served question shows the prompt and the hint, never the answer --------


def _served(content: dict) -> ServedQuestionOut:
    attempt = SimpleNamespace(
        id=5,
        session_id=2,
        ordinal=1,
        requested_difficulty=Difficulty.EASY,
        served_difficulty=Difficulty.EASY,
        subtopic_id=1,
    )
    question = SimpleNamespace(
        id=9,
        question_type=QuestionType.NUMERIC_RESPONSE,
        prompt=content["prompt"],
        content=content,
    )
    served = SimpleNamespace(attempt=attempt, question=question, resumed=False, fallback_used=False)
    return ServedQuestionOut.from_served(served)


def test_the_served_question_carries_only_the_prompt_and_a_form_hint() -> None:
    content = build_content(_draft(value=19.62, explanation="v = g t = 9.81 * 2 = 19.62"))
    out = _served(content)

    assert out.prompt == PROMPT
    assert out.answer_hint == "Give a number with its unit, e.g. in m/s^2."
    assert out.options is None and out.code is None and out.blocks is None
    published = out.model_dump_json()
    assert "19.62" not in published
    assert "explanation" not in published and "tolerance" not in published


def test_the_hint_follows_accepted_units_sig_figs_and_pure_numbers() -> None:
    view = get_type(QuestionType.NUMERIC_RESPONSE).student_view
    restricted = build_content(_draft(accepted_units=["km/h", "m/s"], sig_figs=2))
    assert view(restricted, seed=1).answer_hint == (
        "Give a number with its unit, in km/h or m/s. Use at least 2 significant figures."
    )
    assert view(build_content(_draft(unit="")), seed=1).answer_hint == "Give a number."
