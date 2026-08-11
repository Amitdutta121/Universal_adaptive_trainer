"""LLM provider boundary.

Responsibility
    Own all outbound LLM traffic: provider selection, credentials, model name,
    timeouts, retries. Curriculum proposal, question generation and advisory
    validation call through here so no other module knows which provider is in
    use.

Status
    Implemented for **structured output only**: :func:`get_structured_client`
    returns a client that takes a JSON Schema and returns a dictionary that
    satisfied it. There is deliberately no free-text completion API -- callers
    parse into strict Pydantic models, and a text endpoint would invite
    pattern-matching over prose instead.

    :func:`describe_availability` reports LLM configuration to the UI honestly,
    and :func:`require_llm` fails with a clear configuration error rather than an
    obscure ``None`` dereference.

Allowed dependencies
    ``app.config``, ``app.errors``.
"""

from __future__ import annotations

from app.llm.availability import describe_availability, require_llm
from app.llm.client import (
    AnthropicStructuredClient,
    OpenAICompatibleClient,
    OpenAIStructuredClient,
    OpenRouterStructuredClient,
    StructuredLLMClient,
    get_structured_client,
    to_strict_schema,
)

__all__ = [
    "AnthropicStructuredClient",
    "OpenAICompatibleClient",
    "OpenAIStructuredClient",
    "OpenRouterStructuredClient",
    "StructuredLLMClient",
    "describe_availability",
    "get_structured_client",
    "require_llm",
    "to_strict_schema",
]
