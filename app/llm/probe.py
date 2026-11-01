"""One minimal provider call that proves a role's settings work (Task 42).

Used by the Settings screen's Test button before a configuration may be saved. A chat role
asks for one token; the embeddings role embeds one word and reports the vector dimension.
Failures come back as the provider's own message, never as an exception.
"""

from __future__ import annotations

from dataclasses import dataclass

import openai

from app.config import Settings
from app.errors import AdaptiveTrainerError
from app.llm.client import OPENROUTER_BASE_URL, _as_request_error, is_reasoning_model


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    error: str | None = None
    #: Length of the returned vector; embeddings only.
    dimension: int | None = None


def probe(settings: Settings, *, embeddings: bool) -> ProbeResult:
    """Make the call. ``settings`` is already the candidate role's effective settings."""
    if settings.llm_api_key is None:
        return ProbeResult(ok=False, error="No API key: enter one, or set LLM_API_KEY in .env.")
    client = openai.OpenAI(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url or OPENROUTER_BASE_URL,
        timeout=min(settings.llm_timeout_seconds, 30.0),
        max_retries=0,
    )
    try:
        if embeddings:
            response = client.embeddings.create(model=settings.embedding_model, input=["ping"])
            return ProbeResult(ok=True, dimension=len(response.data[0].embedding))
        # Reasoning models (gpt-5-mini, o4-mini) refuse ``max_tokens``, as in the real client.
        limit = "max_completion_tokens" if is_reasoning_model(settings.llm_model) else "max_tokens"
        client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            **{limit: 16},
        )
        return ProbeResult(ok=True)
    except openai.OpenAIError as exc:
        error: AdaptiveTrainerError = _as_request_error(exc)
        return ProbeResult(ok=False, error=f"{error.message} {error.detail or ''}".strip())
    except (IndexError, AttributeError):
        return ProbeResult(ok=False, error="The provider answered without an embedding.")
