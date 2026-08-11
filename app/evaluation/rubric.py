"""Fixed pedagogical-judge rubric identity and dimension ids."""

from __future__ import annotations

import json
from enum import StrEnum

RUBRIC_VERSION = "pedagogical-judge@1"


class JudgeDimensionId(StrEnum):
    SOURCE_GROUNDING = "source_grounding"
    SUBTOPIC_ALIGNMENT = "subtopic_alignment"
    DIFFICULTY_ALIGNMENT = "difficulty_alignment"
    CLARITY = "clarity"
    AMBIGUITY = "ambiguity"
    PEDAGOGICAL_USEFULNESS = "pedagogical_usefulness"
    INTRO_PYTHON_APPROPRIATENESS = "intro_python_appropriateness"
    ANSWER_EXPLANATION_CONSISTENCY = "answer_explanation_consistency"
    DISTRACTOR_QUALITY = "distractor_quality"
    TEST_QUALITY = "test_quality"


def build_judge_system_prompt() -> str:
    """Return the fixed instructions for a pedagogical question review."""
    dimensions = ", ".join(dimension.value for dimension in JudgeDimensionId)
    return (
        "You are an advisory pedagogical reviewer for introductory Python assessment questions. "
        f"Evaluate every rubric dimension: {dimensions}. "
        "Score each applicable dimension from 1 to 5. For a non-applicable dimension, set "
        "applicable to false and score to null. Give concise rationales and concise issue lists. "
        "The question has already undergone deterministic execution checks; do not re-check "
        "whether code runs or tests execute. Assess its pedagogical quality from the supplied "
        "question, source, and taxonomy context."
    )


def build_judge_user_prompt(
    *,
    question_artifact: dict[str, object],
    source_sections: list[dict[str, object]],
    taxonomy: dict[str, object],
) -> str:
    """Serialize the complete, reviewable question context for the judge."""
    return json.dumps(
        {
            "question_artifact": question_artifact,
            "source_sections": source_sections,
            "taxonomy": taxonomy,
        },
        ensure_ascii=False,
    )
