"""What the agent may only do after the professor clicks, and the cost plans spending needs.

Approval itself is Pydantic AI's: a tool registered with ``requires_approval=True`` never runs
inside the model's turn. The run ends with an AG-UI interrupt naming the call and its arguments;
the tool runs only when the next request resumes it with the professor's ``approved: true``,
which only the chat panel's approval card sends.

Spending has one more step. ``plan_generation`` prices a run with the same dry run as
``POST /generation-runs`` and keeps the target, its model-call count and its course here, under
a short random plan id. ``run_generation`` takes that id and the call count; it refuses an id
this server did not issue, one that expired or was made for another course, and a count that
is not the plan's, so the number on the approval card is the number the run was priced at.

The id is short on purpose: the model copies it from one tool call into the next. A signed
token carrying the whole target (2-3 KB) came back corrupted in the Checkpoint I run. Plans live
in this process only, like the job queue; after a restart the run is planned again.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any

from pydantic import BaseModel

from app.errors import DomainRuleError

#: How long a priced plan can be run before it must be planned again.
PLAN_TTL_SECONDS = 30 * 60

#: The tools that wait for the professor's click. ``test_agent_approvals`` checks this set
#: against the toolset, so a new tool that writes or spends cannot slip in ungated.
APPROVAL_REQUIRED = frozenset(
    {"approve_curriculum", "edit_curriculum", "save_style", "publish_set", "run_generation"}
)


class PlannedRun(BaseModel):
    """What a plan id stands for."""

    course_id: int | None
    target: dict[str, Any]
    model_calls: int


_plans: dict[str, tuple[float, PlannedRun]] = {}
_plans_lock = threading.Lock()


def store_plan(plan: PlannedRun, *, now: float | None = None) -> str:
    """A new plan id for ``plan``, valid for :data:`PLAN_TTL_SECONDS`."""
    now = now or time.time()
    plan_id = f"plan-{secrets.token_hex(4)}"
    with _plans_lock:
        for stale in [key for key, (expires, _) in _plans.items() if expires < now]:
            del _plans[stale]
        _plans[plan_id] = (now + PLAN_TTL_SECONDS, plan)
    return plan_id


def open_plan(
    plan_id: str, *, course_id: int | None, model_calls: int, now: float | None = None
) -> PlannedRun:
    """The plan ``plan_id`` stands for, checked against the course and the approved call count.

    Raises:
        DomainRuleError: the id is unknown, expired, for another course, or ``model_calls`` is
            not the count it was priced at.
    """
    with _plans_lock:
        stored = _plans.get(plan_id.strip())
    if stored is None:
        raise DomainRuleError("This generation plan is not valid. Plan the run again.")
    expires, plan = stored
    if expires < (now or time.time()):
        raise DomainRuleError("This generation plan has expired. Plan the run again.")
    if plan.course_id != course_id:
        raise DomainRuleError("This generation plan was made for another course.")
    if plan.model_calls != model_calls:
        raise DomainRuleError(
            "The approved call count is not the plan's.",
            detail=f"The plan was priced at {plan.model_calls} model calls, not {model_calls}.",
        )
    return plan
