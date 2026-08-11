"""Foundational shared domain entities.

This package holds only the vocabulary that more than one subsystem needs *now*:
enums, value objects and the entity shapes that the professor content pipeline
and the student adaptive engine must agree on.

Rules for this package:

* Pure Python + Pydantic. No database, HTTP, LLM or filesystem imports.
* Add an entity here only when a second module needs it. Subsystem-private
  shapes belong in that subsystem's package.
* These are *not* the database tables. Persistence lives in ``app.persistence``
  and is free to store a subset (see ``docs/DECISIONS.md``).
"""

from app.domain.books import (
    Book,
    BookChapter,
    BookSection,
    ExtractionWarning,
    SectionSource,
)
from app.domain.curriculum import CurriculumVersion, Subtopic, Topic
from app.domain.enums import (
    BookStatus,
    CurriculumStatus,
    Difficulty,
    ExtractionWarningCode,
    GeneratorKind,
    MasteryBand,
    PreferenceCategory,
    PreferenceConfirmationState,
    QuestionKind,
    QuestionStatus,
    RejectionReason,
    ReviewDecision,
    SourceFormat,
    StructureConfidence,
    StructureSource,
    WarningSeverity,
)
from app.domain.feedback import ProfessorReview
from app.domain.mastery import (
    DEFAULT_BKT_PARAMETERS,
    INITIAL_SUBTOPIC_WEAKNESS,
    MAX_SCORE,
    MIN_SCORE,
    BKTParameters,
    difficulty_for_mastery,
    mastery_band,
    score_from_tests,
)
from app.domain.preferences import (
    PROFILE_VERSION,
    PreferenceStatement,
    confidence_from_evidence,
)
from app.domain.questions import Question, QuestionCheck, QuestionValidationReport

__all__ = [
    "DEFAULT_BKT_PARAMETERS",
    "INITIAL_SUBTOPIC_WEAKNESS",
    "MAX_SCORE",
    "MIN_SCORE",
    "PROFILE_VERSION",
    "BKTParameters",
    "Book",
    "BookChapter",
    "BookSection",
    "BookStatus",
    "CurriculumStatus",
    "CurriculumVersion",
    "Difficulty",
    "ExtractionWarning",
    "ExtractionWarningCode",
    "GeneratorKind",
    "MasteryBand",
    "PreferenceCategory",
    "PreferenceConfirmationState",
    "PreferenceStatement",
    "ProfessorReview",
    "Question",
    "QuestionCheck",
    "QuestionKind",
    "QuestionStatus",
    "QuestionValidationReport",
    "RejectionReason",
    "ReviewDecision",
    "SectionSource",
    "SourceFormat",
    "StructureConfidence",
    "StructureSource",
    "Subtopic",
    "Topic",
    "WarningSeverity",
    "confidence_from_evidence",
    "difficulty_for_mastery",
    "mastery_band",
    "score_from_tests",
]
