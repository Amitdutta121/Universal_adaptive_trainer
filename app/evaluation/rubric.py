"""Fixed pedagogical-judge rubric identity and dimension ids."""

from __future__ import annotations

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
