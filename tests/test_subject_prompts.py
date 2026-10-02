"""Phase 2, S1: every prompt is a function of the course's subject profile.

A subject with no code type must not hear about code, programs or tests; the
Python profile must reproduce the shipped constants exactly (the golden file
pins those constants byte for byte).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.domain.enums import JudgeMetricId, RejectionReason
from app.evaluation import judge_learning
from app.evaluation.prompts import (
    JUDGE_ISSUE_CODES,
    RUBRIC_VERSION,
    SYSTEM_PROMPT_FOR,
    TEST_ISSUE_CODES,
    issue_codes_for,
    rubric_version_for,
    system_prompt_for,
)
from app.generation.principles import COMMON_SYSTEM, common_system
from app.subjects import PYTHON_PROFILE, SubjectProfile, profile_for

PYTHON_TYPES = [
    "multiple_choice",
    "true_false",
    "parsons",
    "output_prediction",
    "code_completion",
    "debugging",
    "coding",
]
BANNED = re.compile(r"\b(python|code|program|tests)\b", re.IGNORECASE)


def _course(name: str, subject: str | None, types: list[str] | None) -> SimpleNamespace:
    return SimpleNamespace(name=name, description=None, subject=subject, question_types=types)


PHYSICS = profile_for(
    _course("Mechanics", "physics", ["multiple_choice", "true_false", "numeric_response"])
)
BIOLOGY = profile_for(_course("Cells", "biology", ["multiple_choice", "short_answer"]))
ML = profile_for(_course("LLMs", "ml_llms", None))
ML_WITH_CODE = profile_for(_course("LLMs", "ml_llms", ["multiple_choice", "coding"]))


def _all_prompts(profile: SubjectProfile) -> dict[str, str]:
    prompts = {"generation.system": common_system(profile)}
    for metric in JudgeMetricId:
        prompts[f"judge.system.{metric.value}"] = system_prompt_for(metric, profile)
    prompts["judge_learning.system"] = judge_learning.system_for(profile)
    return prompts


@pytest.mark.parametrize("profile", [PHYSICS, BIOLOGY, ML], ids=["physics", "biology", "ml"])
def test_non_code_prompts_never_mention_code(profile: SubjectProfile) -> None:
    assert not profile.has_code_types
    for name, text in _all_prompts(profile).items():
        assert not BANNED.findall(text), (name, BANNED.findall(text))
        assert f"{profile.phrase} assessment question" in text or name.endswith("generatability"), (
            name
        )


@pytest.mark.parametrize("profile", [PHYSICS, BIOLOGY, ML], ids=["physics", "biology", "ml"])
def test_non_code_issue_codes_drop_the_test_codes(profile: SubjectProfile) -> None:
    codes = issue_codes_for(profile)
    assert not set(codes) & TEST_ISSUE_CODES
    assert set(codes) == set(JUDGE_ISSUE_CODES) - TEST_ISSUE_CODES
    issues_prompt = system_prompt_for(JudgeMetricId.ISSUES, profile)
    for code in codes:
        assert code.value in issues_prompt
    for code in TEST_ISSUE_CODES:
        assert code.value not in issues_prompt


def test_python_profile_reproduces_the_shipped_constants() -> None:
    assert common_system(PYTHON_PROFILE) == COMMON_SYSTEM
    for metric in JudgeMetricId:
        assert system_prompt_for(metric, PYTHON_PROFILE) == SYSTEM_PROMPT_FOR[metric]
    assert judge_learning.system_for(PYTHON_PROFILE) == judge_learning.SYSTEM
    assert issue_codes_for(PYTHON_PROFILE) == JUDGE_ISSUE_CODES
    assert RejectionReason.INCORRECT_TESTS in JUDGE_ISSUE_CODES
    assert rubric_version_for(PYTHON_PROFILE) == RUBRIC_VERSION


def test_a_python_course_gets_the_python_profile() -> None:
    assert profile_for(_course("CS 135", "intro_python", PYTHON_TYPES)) == PYTHON_PROFILE


def test_other_subjects_get_their_own_rubric_version() -> None:
    assert rubric_version_for(PHYSICS) != RUBRIC_VERSION
    assert rubric_version_for(PHYSICS).startswith(f"{RUBRIC_VERSION}+")
    assert rubric_version_for(PHYSICS) != rubric_version_for(BIOLOGY)


def test_legacy_course_is_intro_python_with_the_seven_types() -> None:
    profile = profile_for(_course("Old course", None, None))
    assert profile.subject_id == "intro_python"
    assert profile.phrase == "introductory-Python"
    assert profile.has_code_types
    assert set(profile.question_types) == set(PYTHON_TYPES)
    assert common_system(profile) == COMMON_SYSTEM


def test_physics_course_profile() -> None:
    assert PHYSICS.subject_id == "physics"
    assert PHYSICS.phrase == "physics"
    assert PHYSICS.question_types == ("multiple_choice", "true_false", "numeric_response")
    assert not PHYSICS.has_code_types


def test_physics_course_without_types_keeps_its_defaults() -> None:
    profile = profile_for(_course("Mechanics", "physics", None))
    assert profile.subject_id == "physics"
    assert profile.question_types
    assert not profile.has_code_types


def test_custom_course_is_named_after_the_course() -> None:
    profile = profile_for(_course("Organic Chemistry", "custom", ["multiple_choice"]))
    assert profile.subject_id == "custom"
    assert profile.phrase == "Organic Chemistry"
    assert not profile.has_code_types
    assert "one accurate Organic Chemistry assessment question" in common_system(profile)


def test_unknown_subject_falls_back_to_custom() -> None:
    profile = profile_for(_course("Statistics", "statistics", ["true_false"]))
    assert profile.subject_id == "custom"
    assert profile.phrase == "Statistics"


def test_any_code_type_brings_in_the_code_wording() -> None:
    profile = profile_for(_course("Data science", "custom", ["multiple_choice", "coding"]))
    assert profile.has_code_types
    assert set(issue_codes_for(profile)) == set(JUDGE_ISSUE_CODES)
    assert "any tests agree" in common_system(profile)
    assert "untaught Python\nfeature" in common_system(profile)


def test_an_ml_course_that_picks_a_code_type_gets_the_code_wording() -> None:
    assert ML_WITH_CODE.has_code_types and ML_WITH_CODE.code_language == "Python"
    assert set(issue_codes_for(ML_WITH_CODE)) >= TEST_ISSUE_CODES
    assert "machine-learning assessment question" in common_system(ML_WITH_CODE)
