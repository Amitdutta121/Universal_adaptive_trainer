"""Custom rule judges of a taxonomy: list, create, edit (enable/disable).

Rules belong to one curriculum version; scoped requests enforce course boundaries.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.domain.enums import CustomJudgeKind
from app.errors import DomainRuleError
from app.evaluation.custom import validate_pattern
from app.persistence.models import CustomJudgeRow
from app.persistence.repositories import CurriculumRepository, CustomJudgeRepository
from app.web.routes.api.deps import CourseScope, DbSession, ensure_in_course
from app.web.routes.api.schemas import (
    CreateCustomJudgeRequest,
    CustomJudgeListResponse,
    CustomJudgeOut,
    UpdateCustomJudgeRequest,
)

router = APIRouter(prefix="/custom-judges", tags=["custom-judges"])


def _check_version(session: DbSession, version_id: int, course: int | None) -> None:
    version = CurriculumRepository(session).get_with_tree(version_id)
    ensure_in_course(version.course_id, course, "Curriculum version")


def _validated(fields: dict) -> dict:
    text = fields.get("rule_text")
    if not isinstance(text, str) or not text.strip():
        raise DomainRuleError("A custom judge needs a nonempty rule.")
    fields["rule_text"] = text.strip()
    if fields.get("kind") is None or fields.get("enabled") is None:
        raise DomainRuleError("Kind and enabled cannot be null.")
    if fields["kind"] is CustomJudgeKind.PATTERN:
        pattern = fields.get("pattern")
        if not isinstance(pattern, str):
            raise DomainRuleError("A pattern judge needs a pattern.")
        try:
            validate_pattern(pattern)
        except ValueError as exc:
            raise DomainRuleError(str(exc)) from exc
    elif fields.get("pattern") is not None:
        raise DomainRuleError("Only pattern judges may carry a pattern.")
    return fields


@router.get("", response_model=CustomJudgeListResponse)
def list_custom_judges(
    session: DbSession, course: CourseScope, curriculum_version_id: int
) -> CustomJudgeListResponse:
    """Every custom judge of a taxonomy, enabled or not, oldest first."""
    _check_version(session, curriculum_version_id, course)
    return CustomJudgeListResponse(
        judges=[
            CustomJudgeOut.from_row(row)
            for row in CustomJudgeRepository(session).list_for_version(curriculum_version_id)
        ]
    )


@router.post("", response_model=CustomJudgeOut, status_code=status.HTTP_201_CREATED)
def create_custom_judge(
    session: DbSession, course: CourseScope, body: CreateCustomJudgeRequest
) -> CustomJudgeOut:
    """Add a rule. A ``pattern`` rule must carry a compilable ``pattern``."""
    _check_version(session, body.curriculum_version_id, course)
    row = CustomJudgeRepository(session).add(CustomJudgeRow(**_validated(body.model_dump())))
    session.commit()
    return CustomJudgeOut.from_row(row)


@router.patch("/{judge_id}", response_model=CustomJudgeOut)
def update_custom_judge(
    session: DbSession, course: CourseScope, judge_id: int, body: UpdateCustomJudgeRequest
) -> CustomJudgeOut:
    """Change a rule's text, kind, pattern, or enabled flag."""
    repository = CustomJudgeRepository(session)
    row = repository.get(judge_id)
    _check_version(session, row.curriculum_version_id, course)
    fields = {name: getattr(row, name) for name in ("rule_text", "kind", "pattern", "enabled")}
    updates = body.model_dump(exclude_unset=True)
    if "kind" in updates and updates["kind"] is CustomJudgeKind.LLM and "pattern" not in updates:
        updates["pattern"] = None
    fields.update(updates)
    row = repository.update(judge_id, **_validated(fields))
    session.commit()
    return CustomJudgeOut.from_row(row)
