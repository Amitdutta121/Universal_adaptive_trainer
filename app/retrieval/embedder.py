"""Turning text into embedding vectors, through the configured provider.

Deliberately small and separate from :mod:`app.llm.client`, which only does
structured chat completions. The one live transport is OpenRouter's
OpenAI-compatible ``/embeddings`` endpoint (verified to serve
``openai/text-embedding-3-small``); the client is the same ``openai`` SDK the
chat path already depends on, pointed at the OpenRouter base URL.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import openai

from app.config import Settings
from app.errors import LLMRequestError
from app.llm.availability import require_llm
from app.llm.client import OPENROUTER_BASE_URL

#: text-embedding-3-small rejects any input over 8192 tokens. A handful of
#: production sections are longer, so the vector is built from a truncated copy
#: while the stored section text stays whole. Deliberately conservative: dense
#: prose and code listings run well under 4 chars/token (a 23.5k-char section was
#: measured over the cap), so 18k chars keeps every real section inside 8192.
MAX_EMBED_CHARS = 18_000

#: Inputs per provider request.
DEFAULT_BATCH_SIZE = 32

#: A request also stops accumulating inputs once their combined length reaches
#: this, so a batch of large sections cannot build an oversized request body
#: (the failure mode when the whole book was sent in 64-input batches).
MAX_BATCH_CHARS = 90_000

#: Attempts per request before giving up, with a short linear backoff. The
#: backfill is a batch job, so a transient provider hiccup mid-run should not
#: lose the sections already embedded.
MAX_REQUEST_ATTEMPTS = 3


@runtime_checkable
class Embedder(Protocol):
    """Embeds text. ``model`` names the vector space the outputs live in."""

    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per input, in the same order. Empty input -> empty list."""
        ...


@dataclass
class OpenRouterEmbedder:
    """The live embedder: OpenRouter's OpenAI-compatible embeddings endpoint."""

    model: str
    api_key: str
    base_url: str = OPENROUTER_BASE_URL
    batch_size: int = DEFAULT_BATCH_SIZE
    timeout_seconds: float = 60.0
    _client: openai.OpenAI = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url or OPENROUTER_BASE_URL,
            timeout=self.timeout_seconds,
            max_retries=1,
            default_headers={
                "HTTP-Referer": "https://localhost/adaptive-trainer",
                "X-Title": "Adaptive Trainer",
            },
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        clipped = [text[:MAX_EMBED_CHARS] for text in texts]
        out: list[list[float]] = []
        for batch in self._batches(clipped):
            out.extend(self._embed_one_request(batch))
        return out

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        """Split into requests bounded by both input count and total characters."""
        batches: list[list[str]] = []
        current: list[str] = []
        current_chars = 0
        for text in texts:
            too_many = len(current) >= self.batch_size
            too_long = current and current_chars + len(text) > MAX_BATCH_CHARS
            if too_many or too_long:
                batches.append(current)
                current, current_chars = [], 0
            current.append(text)
            current_chars += len(text)
        if current:
            batches.append(current)
        return batches

    def _embed_one_request(self, batch: list[str]) -> list[list[float]]:
        last: Exception | None = None
        for attempt in range(1, MAX_REQUEST_ATTEMPTS + 1):
            try:
                response = self._client.embeddings.create(model=self.model, input=batch)
                ordered = sorted(response.data, key=lambda item: item.index)
                return [list(item.embedding) for item in ordered]
            except openai.BadRequestError as exc:
                # A 400 is deterministic (usually an input still over the token
                # cap) -- retrying wastes calls; surface it with enough context.
                raise LLMRequestError(
                    "The embedding provider rejected an input.",
                    detail=f"{str(getattr(exc, 'message', None) or exc)[:300]} "
                    f"(batch of {len(batch)}, longest {max(len(t) for t in batch)} chars)",
                ) from exc
            except openai.OpenAIError as exc:  # transport or transient provider failure
                last = exc
                if attempt < MAX_REQUEST_ATTEMPTS:
                    time.sleep(attempt)
        raise LLMRequestError(
            "The embedding provider could not be reached.",
            detail=str(getattr(last, "message", None) or last)[:400],
        ) from last


def get_embedder(settings: Settings) -> OpenRouterEmbedder:
    """Build the live embedder, raising if no provider/credentials are configured.

    Raises:
        ConfigurationError: via :func:`require_llm` when the app has no LLM key.
    """
    require_llm(settings)
    assert settings.llm_api_key is not None  # require_llm guarantees this
    return OpenRouterEmbedder(
        model=settings.embedding_model,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url or OPENROUTER_BASE_URL,
        timeout_seconds=settings.llm_timeout_seconds,
    )
