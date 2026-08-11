"""Embedding helpers for review-example retrieval."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import openai

from app.config import Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError
from app.llm.availability import require_llm
from app.llm.client import OPENROUTER_BASE_URL


class Embedder(Protocol):
    @property
    def model_id(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def example_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FakeEmbedder:
    def __init__(self, dim: int = 8) -> None:
        self._dim = dim

    @property
    def model_id(self) -> str:
        return "fake/embeddings"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [((digest[i % len(digest)] / 255.0) * 2 - 1) for i in range(self._dim)]
            out.append(vec)
        return out


class OpenRouterEmbedder:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = require_llm(settings or get_settings())
        key = self._settings.llm_api_key
        if key is None:
            raise ConfigurationError("LLM API key is required for embeddings.")
        self._client = openai.OpenAI(
            api_key=key.get_secret_value(),
            base_url=self._settings.llm_base_url or OPENROUTER_BASE_URL,
            timeout=self._settings.llm_timeout_seconds,
        )
        self._model = self._settings.embedding_model

    @property
    def model_id(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except openai.OpenAIError as exc:
            raise LLMRequestError("Embedding request failed.", detail=str(exc)[:400]) from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]


def get_embedder(settings: Settings | None = None) -> Embedder:
    return OpenRouterEmbedder(settings)
