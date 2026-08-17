"""The JSON API.

Every professor capability is exposed here as JSON under ``/api``, and the
server-rendered pages in :mod:`app.web.routes.pages` call these same handler
functions rather than repeating the work (ADR-027). That keeps one implementation
per capability, so a future React client and the current HTML UI cannot drift.

Handlers are plain functions: FastAPI resolves ``DbSession`` when it serves a
request, and the page routes pass a session in directly. Errors are raised, not
returned -- the handlers in :mod:`app.errors` render them as JSON for ``/api``
paths and as an HTML error page elsewhere.
"""

from fastapi import APIRouter

from app.web.routes.api import (
    books,
    calibration,
    coverage,
    curriculum,
    evaluation,
    feedback,
    instructions,
    judge_prompts,
    questions,
    students,
    system,
)

router = APIRouter(prefix="/api")
router.include_router(system.router)
router.include_router(books.router)
router.include_router(curriculum.router)
router.include_router(questions.router)
router.include_router(feedback.router)
router.include_router(instructions.router)
router.include_router(judge_prompts.router)
router.include_router(calibration.router)
router.include_router(coverage.router)
router.include_router(students.router)
# After ``questions``: this router also serves /questions/{id}/evaluations, and
# including it first would let that path shadow /questions/{question_id}.
router.include_router(evaluation.router)

__all__ = [
    "books",
    "calibration",
    "coverage",
    "curriculum",
    "evaluation",
    "feedback",
    "instructions",
    "judge_prompts",
    "questions",
    "router",
    "students",
    "system",
]
