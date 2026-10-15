"""What the agent may only do after the professor clicks, and the signed cost plans spending needs.

Approval itself is Pydantic AI's: a tool registered with ``requires_approval=True`` never runs
inside the model's turn. The run ends with an AG-UI interrupt naming the call and its arguments;
the tool runs only when the next request resumes it with the professor's ``approved: true``,
which only the chat panel's approval card sends.

Spending has one more step. ``plan_generation`` prices a run with the same dry run as
``POST /generation-runs`` and returns a plan id: the target and its model-call count, signed
with a key derived from ``AUTH_SECRET_KEY`` and bound to the course. ``run_generation`` takes
that id and the call count; it refuses an id that was altered, expired or made for another
course, and a count that is not the plan's, so the number on the approval card is the number
the run was priced at.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.errors import DomainRuleError

#: How long a priced plan can be run before it must be planned again.
PLAN_TTL_SECONDS = 30 * 60
_PLAN_INFO = b"adaptive-trainer/agent/generation-plan"

#: The tools that wait for the professor's click. ``test_agent_approvals`` checks this set
#: against the toolset, so a new tool that writes or spends cannot slip in ungated.
APPROVAL_REQUIRED = frozenset(
    {"approve_curriculum", "edit_curriculum", "save_style", "publish_set", "run_generation"}
)


class SignedPlan(BaseModel):
    """What a plan id carries."""

    course_id: int | None
    target: dict[str, Any]
    model_calls: int


def _key(settings: Settings) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_PLAN_INFO).derive(
        settings.auth_secret_key.get_secret_value().encode()
    )


def _sign(body: str, settings: Settings) -> str:
    return hmac.new(_key(settings), body.encode(), hashlib.sha256).hexdigest()


def sign_plan(
    plan: SignedPlan, *, settings: Settings | None = None, now: float | None = None
) -> str:
    """A plan id for ``plan``, valid for :data:`PLAN_TTL_SECONDS`."""
    settings = settings or get_settings()
    expires = int((now or time.time()) + PLAN_TTL_SECONDS)
    payload = base64.urlsafe_b64encode(plan.model_dump_json().encode()).decode()
    body = f"{expires}.{payload}"
    return f"{body}.{_sign(body, settings)}"


def open_plan(
    plan_id: str,
    *,
    course_id: int | None,
    model_calls: int,
    settings: Settings | None = None,
    now: float | None = None,
) -> SignedPlan:
    """The plan ``plan_id`` carries, checked against the course and the approved call count.

    Raises:
        DomainRuleError: the id is malformed, altered, expired, for another course, or
            ``model_calls`` is not the count it was priced at.
    """
    settings = settings or get_settings()
    body, _, signature = plan_id.rpartition(".")
    expires, _, payload = body.partition(".")
    if not (
        expires.isdigit() and payload and hmac.compare_digest(signature, _sign(body, settings))
    ):
        raise DomainRuleError("This generation plan is not valid. Plan the run again.")
    if int(expires) < (now or time.time()):
        raise DomainRuleError("This generation plan has expired. Plan the run again.")
    plan = SignedPlan.model_validate(json.loads(base64.urlsafe_b64decode(payload)))
    if plan.course_id != course_id:
        raise DomainRuleError("This generation plan was made for another course.")
    if plan.model_calls != model_calls:
        raise DomainRuleError(
            "The approved call count is not the plan's.",
            detail=f"The plan was priced at {plan.model_calls} model calls, not {model_calls}.",
        )
    return plan
