"""``POST /agent``: the professor agent over AG-UI, for the Studio's chat panel (Phase 8).

The body is an AG-UI ``RunAgentInput`` and the response is its event stream. The run works in
the request's course (``X-Course-Id``) as the logged-in professor, and spends model credit, so
it needs a verified email like every other LLM route (ADR-061). A tool that needs the
professor's approval ends the run with an AG-UI interrupt; the client resumes it with the
professor's answer in ``resume``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic_ai.models import Model
from pydantic_ai.ui.ag_ui import AGUIAdapter
from pydantic_ai.ui.ag_ui._interrupt import interrupt_id_to_tool_call_id

# Modules, not names: ``app.agent.tools`` imports route modules, so either side may load first.
from app.agent import agent as professor
from app.agent import threads as agent_threads
from app.agent import tools as agent_tools
from app.agent.attachments import describe_attachments
from app.errors import DomainRuleError
from app.ingestion.youtube import AvailabilityCheck, TranscriptFetch
from app.jobs.queue import JobQueueDep
from app.llm.client import StructuredLLMClient
from app.persistence.database import get_session_factory
from app.web.routes.api.books import get_youtube_check, get_youtube_fetch
from app.web.routes.api.coverage import GenerationClientDep
from app.web.routes.api.curriculum import get_draft_client
from app.web.routes.api.deps import SPENDS_LLM_CREDIT, CourseScope, CurrentUser, DbSession
from app.web.routes.api.generation_runs import _query_embedder
from app.web.routes.api.schemas import (
    AgentThreadListResponse,
    AgentThreadOut,
    AgentThreadSave,
    AgentThreadSummary,
)
from app.web.routes.api.setup import SetupClientDep

router = APIRouter(prefix="/agent", tags=["agent"])


class CopilotKitAGUIAdapter(AGUIAdapter):
    """Pydantic AI's AG-UI adapter, minus CopilotKit's echo of an approval.

    On a resume, CopilotKit (1.79) also sends the professor's answer as the paused call's
    ``tool`` message. Pydantic AI would read that as the call's result and refuse the resume
    ("already executed"), so the approved tool never ran. Dropping the echo leaves ``resume`` as
    the only answer, still deny-by-default. A ``tool`` message is never an approval by itself:
    the gated tool does not run for it.
    """

    @classmethod
    def build_run_input(cls, body: bytes):
        run_input = super().build_run_input(body)
        # Files attached in the chat reach the model as text it can read (ADR-076).
        run_input = run_input.model_copy(
            update={"messages": describe_attachments(list(run_input.messages))}
        )
        resumed = {interrupt_id_to_tool_call_id(e.interrupt_id) for e in run_input.resume or []}
        if not resumed:
            return run_input
        messages = [
            m for m in run_input.messages if not (m.role == "tool" and m.tool_call_id in resumed)
        ]
        return run_input.model_copy(update={"messages": messages})


def get_agent_model() -> Model:
    """The chat model, read from settings per request; tests override it with a fake."""
    return professor.agent_model()


@router.post("", dependencies=SPENDS_LLM_CREDIT, response_class=Response)
async def run_agent(
    request: Request,
    course: CourseScope,
    user: CurrentUser,
    queue: JobQueueDep,
    model: Annotated[Model, Depends(get_agent_model)],
    draft_client: Annotated[StructuredLLMClient | None, Depends(get_draft_client)],
    generation_client: GenerationClientDep,
    setup_client: SetupClientDep,
    youtube_fetch: Annotated[TranscriptFetch, Depends(get_youtube_fetch)],
    youtube_check: Annotated[AvailabilityCheck, Depends(get_youtube_check)],
) -> Response:
    """Run the agent on an AG-UI ``RunAgentInput`` and stream its events back."""
    deps = agent_tools.AgentDeps(
        session_factory=get_session_factory(),
        course_id=course,
        user_id=user.id,
        queue=queue,
        draft_client=draft_client,
        generation_client=generation_client,
        setup_client=setup_client,
        youtube_fetch=youtube_fetch,
        youtube_check=youtube_check,
        embedder=lambda: _query_embedder(request),
    )
    return await CopilotKitAGUIAdapter.dispatch_request(
        request, agent=professor.professor_agent, model=model, deps=deps
    )


# -- Saved chats (ADR-075) -------------------------------------------------------------------


def _course(course: int | None) -> int:
    if course is None:
        raise DomainRuleError("Chats belong to a course; open one first.")
    return course


def _out(row) -> AgentThreadOut:
    return AgentThreadOut(
        id=row.id, title=row.title, updated_at=row.updated_at, messages=row.messages
    )


@router.get("/threads", response_model=AgentThreadListResponse)
def list_threads(session: DbSession, course: CourseScope, user: CurrentUser):
    """The professor's chats in this course, most recently used first."""
    rows = agent_threads.list_threads(session, _course(course), user.id)
    return AgentThreadListResponse(
        threads=[
            AgentThreadSummary(id=row.id, title=row.title, updated_at=row.updated_at)
            for row in rows
        ]
    )


@router.get("/threads/{thread_id}", response_model=AgentThreadOut)
def get_thread(session: DbSession, course: CourseScope, user: CurrentUser, thread_id: uuid.UUID):
    return _out(agent_threads.get_thread(session, thread_id, _course(course), user.id))


@router.put("/threads/{thread_id}", response_model=AgentThreadOut)
def save_thread(
    session: DbSession,
    course: CourseScope,
    user: CurrentUser,
    thread_id: uuid.UUID,
    body: AgentThreadSave,
):
    """Create the chat or replace its messages; the panel saves after every run."""
    row = agent_threads.save_thread(session, thread_id, _course(course), user.id, body.messages)
    return _out(row)


@router.delete("/threads/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thread(
    session: DbSession, course: CourseScope, user: CurrentUser, thread_id: uuid.UUID
) -> Response:
    agent_threads.delete_thread(session, thread_id, _course(course), user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
