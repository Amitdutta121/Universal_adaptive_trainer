"""A scripted stand-in for the agent's chat model, and agent deps over the test database.

:func:`scripted` returns a Pydantic AI ``FunctionModel`` that makes the given tool calls, one
model turn each, and then answers with text. No test reaches a provider.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel

from app.agent.tools import AgentDeps
from app.persistence.database import get_session_factory

PROFESSOR_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


class InlineQueue:
    """Runs submitted work at once, as ``TestClient``'s background tasks do."""

    def __init__(self) -> None:
        self.submitted: list[str] = []

    def submit(self, func, /, *args, **kwargs) -> None:
        self.submitted.append(func.__name__)
        func(*args, **kwargs)


def agent_deps(course_id: int | None = None, **overrides: Any) -> AgentDeps:
    return AgentDeps(
        session_factory=get_session_factory(),
        course_id=course_id,
        user_id=PROFESSOR_ID,
        queue=overrides.pop("queue", None) or InlineQueue(),
        **overrides,
    )


def tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def scripted(*calls: tuple[str, dict[str, Any]], final: str = "Done.") -> FunctionModel:
    """Call each ``(tool_name, args)`` in its own turn, then answer ``final``."""

    def turn_of(messages: list[ModelMessage]) -> int:
        return sum(isinstance(message, ModelResponse) for message in messages)

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        turn = turn_of(messages)
        if turn < len(calls):
            name, args = calls[turn]
            return ModelResponse(
                parts=[ToolCallPart(name, json.dumps(args), tool_call_id=f"call-{turn}")]
            )
        return ModelResponse(parts=[TextPart(final)])

    async def stream(
        messages: list[ModelMessage], _info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        turn = turn_of(messages)
        if turn < len(calls):
            name, args = calls[turn]
            yield {0: DeltaToolCall(name, json.dumps(args), tool_call_id=f"call-{turn}")}
        else:
            yield final

    return FunctionModel(respond, stream_function=stream)


def result_of(messages: list[ModelMessage], tool_name: str) -> Any:
    """The (last) return value of ``tool_name`` in a finished run's messages."""
    found = [part.content for part in tool_returns(messages) if part.tool_name == tool_name]
    assert found, f"{tool_name} was not called"
    return found[-1]
