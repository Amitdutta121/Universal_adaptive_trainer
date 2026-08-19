"""The JSON API.

Every professor and student capability exposed over HTTP lives here under
``/api``. Handlers are plain functions: FastAPI resolves ``DbSession`` when it
serves a request, and expected failures are raised rather than returned so the
shared error handlers in :mod:`app.errors` can serialize them uniformly.
"""

from fastapi import APIRouter, Depends

from app.auth.backend import current_active_user
from app.web.routes.api import (
    auth,
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
router.include_router(auth.router)

#: Every professor content-generation router requires a logged-in professor.
#: ``students`` is deliberately absent here -- it mixes professor-only reads
#: with the anonymous student join/session flow, so it protects its own
#: routes individually instead (see the ``dependencies=`` on those handlers).
_professor_only = [
    books.router,
    curriculum.router,
    questions.router,
    feedback.router,
    instructions.router,
    judge_prompts.router,
    calibration.router,
    coverage.router,
]
for professor_router in _professor_only:
    router.include_router(professor_router, dependencies=[Depends(current_active_user)])

router.include_router(students.router)
# After ``questions``: this router also serves /questions/{id}/evaluations, and
# including it first would let that path shadow /questions/{question_id}.
router.include_router(evaluation.router, dependencies=[Depends(current_active_user)])

__all__ = [
    "auth",
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
