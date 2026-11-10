"""The JSON API.

Every professor and student capability exposed over HTTP lives here under
``/api``. Handlers are plain functions: FastAPI resolves ``DbSession`` when it
serves a request, and expected failures are raised rather than returned so the
shared error handlers in :mod:`app.errors` can serialize them uniformly.
"""

from fastapi import APIRouter, Depends

from app.auth.backend import current_active_user
from app.web.routes.api import (
    agent,
    auth,
    books,
    calibration,
    courses,
    coverage,
    curriculum,
    custom_judges,
    evaluation,
    experimental_recipes,
    feedback,
    figures,
    generation_runs,
    instructions,
    jobs,
    judge_prompts,
    judges,
    questions,
    retrieval,
    rounds,
    settings,
    setup,
    students,
    system,
    tutorials,
)

router = APIRouter(prefix="/api")
router.include_router(system.router)
router.include_router(auth.router)

#: Every professor content-generation router requires a logged-in professor.
#: ``students`` is deliberately absent here -- it mixes professor-only reads
#: with the anonymous student join/session flow, so it protects its own
#: routes individually instead (see the ``dependencies=`` on those handlers).
_professor_only = [
    courses.router,
    books.router,
    curriculum.router,
    questions.router,
    generation_runs.router,
    feedback.router,
    instructions.router,
    instructions.guidelines_router,
    judge_prompts.router,
    judges.router,
    calibration.router,
    coverage.router,
    retrieval.router,
    setup.router,
    rounds.router,
    custom_judges.router,
    jobs.router,
    settings.router,
    tutorials.router,
    experimental_recipes.router,
    agent.router,
]
for professor_router in _professor_only:
    router.include_router(professor_router, dependencies=[Depends(current_active_user)])

router.include_router(students.router)
# Public like the student flow: a student's ``<img>`` cannot send the learner token, and the
# keys are content hashes, so a figure cannot be found without being given its key.
router.include_router(figures.router)
# After ``questions``: this router also serves /questions/{id}/evaluations, and
# including it first would let that path shadow /questions/{question_id}.
router.include_router(evaluation.router, dependencies=[Depends(current_active_user)])

__all__ = [
    "auth",
    "books",
    "calibration",
    "courses",
    "coverage",
    "curriculum",
    "custom_judges",
    "evaluation",
    "feedback",
    "figures",
    "instructions",
    "judge_prompts",
    "judges",
    "questions",
    "retrieval",
    "rounds",
    "router",
    "settings",
    "setup",
    "students",
    "system",
    "tutorials",
]
