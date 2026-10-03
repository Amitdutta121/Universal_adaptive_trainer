"""The style library and the setup suggester.

Phase 0 contract (docs/QUESTION_SETUP_PLAN.md, agent A): fixed signatures, no behaviour yet.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.llm import StructuredLLMClient
from app.styles.schema import QuestionStyle, SetupSuggestion


def get_library(subject: str) -> list[QuestionStyle]:
    """Every style in the library of one subject, in display order.

    ``subject`` is a subject storage key (``SubjectProfile.storage_key``, e.g.
    ``intro_python``). A subject with no curated library returns ``[]`` -- never raises -- so
    the setup modal can say "no styles for this subject yet". Pure: no I/O, no model call.
    """
    raise NotImplementedError("app.styles.library.get_library is a Phase 0 stub")


def suggest_setup(
    session: Session,
    curriculum_version_id: int,
    *,
    client: StructuredLLMClient | None = None,
) -> SetupSuggestion:
    """Suggest library styles per subtopic and a target per cell for one approved taxonomy.

    One structured model call over (subtopics x the subject's library). Every returned style id
    is validated against :func:`get_library`; unknown ids are dropped, not passed through. Every
    visible subtopic of the version appears in ``subtopics`` (possibly with no styles), and every
    subtopic x difficulty cell gets one :class:`CellTarget` bounded to
    ``MIN_CELL_TARGET..MAX_CELL_TARGET`` (default ``MIN_QUESTIONS_PER_CELL``). Persists nothing.

    Raises:
        NotFoundError: the curriculum version does not exist.
        DomainRuleError: the version is not approved.
        LLMRequestError / MalformedModelOutputError: the model call failed.
    """
    raise NotImplementedError("app.styles.library.suggest_setup is a Phase 0 stub")
