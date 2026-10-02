"""Equation response (T2): generated, validated, scored and served through its type module."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import book_documents as docs
import pytest
from fastapi.testclient import TestClient
from llm_fakes import MetricJudgeClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adaptive.scoring import score_answer
from app.assessment import catalog
from app.assessment.specs import Unmarkable, plan_for
from app.curriculum import TaxonomyImportService
from app.domain.enums import Difficulty, QuestionKind, QuestionStatus, QuestionType
from app.domain.questions import Question
from app.generation.schemas import build_content, prompt_fields_from_draft, response_model_for
from app.generation.service import GenerationService
from app.ingestion import BookImportService
from app.persistence.repositories import QuestionRepository
from app.question_types import get_type, implemented_types
from app.question_types.equation_response import EquationResponseDraft
from app.validation.runner import LocalCodeRunner
from app.web.routes.api.schemas import ServedQuestionOut
from graders import get_grader

TYPE = get_type(QuestionType.EQUATION_RESPONSE)
FORBIDDEN_IN_INSTRUCTION = ("python", "code", "program", "tests")


def _draft(**overrides: Any) -> EquationResponseDraft:
    fields: dict[str, Any] = {
        "topic_id": 1,
        "subtopic_ids": [1],
        "prompt": "Differentiate f(x) = x^2 sin(x) with respect to x. Use the variable x.",
        "expected": "2*x*sin(x) + x**2*cos(x)",
        "variables": ["x"],
        "explanation": "Product rule: (uv)' = u'v + uv'.",
        **overrides,
    }
    return EquationResponseDraft(**fields)


def _content(**overrides: Any) -> dict:
    return build_content(_draft(**overrides))


def _question(content: dict) -> Question:
    return Question(
        id=1,
        prompt=content["prompt"],
        question_type=QuestionType.EQUATION_RESPONSE,
        kind=QuestionKind.DISCRETE,
        difficulty=Difficulty.EASY,
        content=content,
    )


# --- the module ---------------------------------------------------------------------------------


def test_the_type_is_built_discrete_and_offerable() -> None:
    assert QuestionType.EQUATION_RESPONSE in implemented_types()
    assert TYPE.kind is QuestionKind.DISCRETE
    assert response_model_for(QuestionType.EQUATION_RESPONSE) is EquationResponseDraft
    assert catalog.TYPES_BY_ID["equation_response"].implemented
    assert catalog.is_offerable("equation_response")
    assert "equation_response" in catalog.default_types_for("physics")


def test_the_instruction_is_subject_neutral_and_states_the_answer_syntax() -> None:
    text = TYPE.instruction.lower()
    assert not [word for word in FORBIDDEN_IN_INSTRUCTION if word in text]
    assert "^" in TYPE.instruction and "left = right" in TYPE.instruction
    assert "variables" in TYPE.instruction


def test_the_draft_fills_the_legacy_columns() -> None:
    assert prompt_fields_from_draft(_draft()) == (_draft().prompt, _draft().expected, None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"variables": ["x", "x"]},
        {"variables": ["2x"]},
        {"variables": ["x__y"]},
        {"expected": "y = 2*x", "variables": ["x", "y"]},  # '=' without equation mode
        {"expected": "2*x", "equation": True},  # equation mode without '='
        {"allowed_functions": ["eval"]},
        {"explanation": ""},
    ],
)
def test_a_malformed_draft_is_refused(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        _draft(**overrides)


def test_the_grading_plan_is_a_symbolic_spec_the_grader_accepts() -> None:
    plan = plan_for(QuestionType.EQUATION_RESPONSE, _content())
    assert plan.capability == "symbolic.expression_equivalence"
    assert plan.spec == {
        "expected": "2*x*sin(x) + x**2*cos(x)",
        "variables": ["x"],
        "equation": False,
        "explanation": "Product rule: (uv)' = u'v + uv'.",
    }
    assert get_grader(plan.capability).check_spec(plan.spec) == []

    restricted = plan_for(QuestionType.EQUATION_RESPONSE, _content(allowed_functions=["sin"]))
    assert restricted.spec["allowed_functions"] == ["sin"]


@pytest.mark.parametrize(
    "content",
    [{"variables": ["x"]}, {"expected": "x", "variables": "x"}, {"expected": " "}],
)
def test_content_without_an_answer_is_unmarkable(content: dict) -> None:
    with pytest.raises(Unmarkable):
        plan_for(QuestionType.EQUATION_RESPONSE, content)


def test_authoring_checks_pass_a_sound_question() -> None:
    checks = TYPE.authoring_checks(_content(), LocalCodeRunner())
    assert {check.name: check.passed for check in checks} == {
        "equation_explanation_present": True,
        "equation_answer_not_in_prompt": True,
    }


def test_a_prompt_that_states_the_answer_fails() -> None:
    content = _content(prompt="Show that the derivative is 2*x*sin(x) +  x**2*cos(x).")
    (leak,) = [
        check
        for check in TYPE.authoring_checks(content, LocalCodeRunner())
        if check.name == "equation_answer_not_in_prompt"
    ]
    assert leak.passed is False
    assert "2*x*sin(x)" in (leak.evidence or "")


def test_a_lone_symbol_answer_is_not_counted_as_given_away() -> None:
    content = _content(prompt="Which variable is the speed? Use v.", expected="v", variables=["v"])
    assert all(check.passed for check in TYPE.authoring_checks(content, LocalCodeRunner()))


# --- generation (fake LLM) -----------------------------------------------------------------------


def _seed(session: Session, settings: Any) -> tuple[object, object, object, int]:
    book = BookImportService(session, settings).import_upload(
        filename="book.json", data=docs.to_bytes(docs.minimal())
    )
    version = TaxonomyImportService(session, settings).import_upload(
        filename="taxonomy.json",
        data=(
            b'{"schema_version":"1","label":"Calculus","topics":['
            b'{"name":"Derivatives","subtopics":[{"name":"Product rule"}]}]}'
        ),
    )
    session.commit()
    return (
        version,
        version.topics[0],
        version.topics[0].subtopics[0],
        book.chapters[0].sections[0].id,
    )


def test_a_fake_llm_draft_is_generated_stored_and_validated(session: Session, settings) -> None:
    version, topic, subtopic, section_id = _seed(session, settings)
    client = MetricJudgeClient(draft=_draft(topic_id=topic.id, subtopic_ids=[subtopic.id]))

    (row,) = GenerationService(session, client=client).generate_for_sections(
        curriculum_version_id=version.id,
        question_type=QuestionType.EQUATION_RESPONSE,
        difficulty=Difficulty.EASY,
        source_section_ids=[section_id],
    )

    stored = QuestionRepository(session).get(row.id)
    assert stored.question_type is QuestionType.EQUATION_RESPONSE
    assert stored.kind is QuestionKind.DISCRETE
    assert stored.reference_solution == "2*x*sin(x) + x**2*cos(x)"
    assert stored.content["variables"] == ["x"]
    report = stored.validation_report
    assert report is not None and report.passed, [c for c in report.checks if not c.passed]
    assert {"equation_explanation_present", "equation_answer_not_in_prompt"} <= {
        check.name for check in report.checks
    }
    assert stored.status is not QuestionStatus.VALIDATION_FAILED
    call = client.generation_calls[0]
    assert call["model"] is EquationResponseDraft
    assert TYPE.instruction in call["prompt"]


# --- scoring --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "score"),
    [
        ("x*(2*sin(x)+x*cos(x))", 100.0),
        ("2x sin(x) + x^2 cos(x)", 100.0),
        ("2*x*cos(x) + x**2*sin(x)", 0.0),
        ("__import__('os')", 0.0),
    ],
)
def test_answers_are_scored_by_equivalence(answer: str, score: float) -> None:
    result = score_answer(_question(_content()), answer)
    assert result.score == score
    assert result.detail == "Product rule: (uv)' = u'v + uv'."


def test_an_injection_attempt_is_a_format_error_not_a_grade() -> None:
    plan = plan_for(QuestionType.EQUATION_RESPONSE, _content())
    result = get_grader(plan.capability).grade(plan.spec, plan.rewrite_answer("__import__('os')"))
    assert result.score == 0.0
    assert result.format_error


def test_equation_mode_accepts_a_multiple_of_the_relation() -> None:
    content = _content(
        prompt="Write the line through the origin with slope 2, in x and y.",
        expected="y = 2*x",
        variables=["x", "y"],
        equation=True,
    )
    assert score_answer(_question(content), "2y = 4x").score == 100.0
    assert score_answer(_question(content), "y = 3x").score == 0.0


# --- the course and the student view -------------------------------------------------------------


def test_a_physics_course_can_offer_equation_response(client: TestClient) -> None:
    created = client.post(
        "/api/courses",
        json={"name": "Physics 1", "subject": "physics", "question_types": ["equation_response"]},
    )
    assert created.status_code == 201, created.text
    course = created.json()
    assert course["question_types"] == ["equation_response"]
    assert course["capabilities"] == ["symbolic.expression_equivalence"]


def test_the_served_question_shows_the_prompt_and_hint_but_never_the_answer() -> None:
    content = _content(
        prompt="Write the kinetic energy of a mass m moving at speed v.",
        expected="m*v^2/2",
        variables=["m", "v"],
        explanation="Kinetic energy is one half m v squared.",
    )
    question = _question(content)
    served = SimpleNamespace(
        attempt=SimpleNamespace(
            id=11,
            session_id=3,
            ordinal=1,
            requested_difficulty=Difficulty.EASY,
            served_difficulty=Difficulty.EASY,
            subtopic_id=None,
        ),
        question=question,
        resumed=False,
        fallback_used=False,
    )

    out = ServedQuestionOut.from_served(served).model_dump(mode="json")

    assert out["prompt"] == content["prompt"]
    assert out["answer_hint"] == (
        "Write an expression using m and v. "
        "Use ^ for powers (x^2) and * for multiplication; 2x also means 2*x."
    )
    assert out["options"] is None and out["code"] is None and out["blocks"] is None
    text = repr(out)
    assert "m*v^2/2" not in text and "one half" not in text


def test_the_hint_names_the_equation_form_and_restricted_functions() -> None:
    hint = TYPE.student_view(
        _content(
            expected="y = sin(x)", variables=["x", "y"], equation=True, allowed_functions=["sin"]
        ),
        seed=0,
    ).answer_hint
    assert hint is not None
    assert hint.startswith("Write an equation, left = right, using x and y.")
    assert hint.endswith("Functions you may use: sin.")
    assert "sin(x)" not in hint
