"""Tests for the Instructor-backed structured-output LLM client."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from instructor.core import InstructorRetryException
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import LLMProvider, Settings
from app.errors import ConfigurationError, LLMRequestError, MalformedModelOutputError
from app.llm import client as client_module
from app.llm import get_structured_client
from app.llm.client import OPENROUTER_BASE_URL, InstructorStructuredClient


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


def openrouter_settings(**overrides: Any) -> Settings:
    data = {
        "_env_file": None,
        "llm_provider": LLMProvider.OPENROUTER,
        "llm_model": "deepseek/deepseek-chat",
        "llm_api_key": "sk-or-test",
        "llm_timeout_seconds": 5.0,
        "llm_max_output_tokens": 256,
    }
    data.update(overrides)
    return Settings(**data)  # type: ignore[call-arg]


def client_with_create(
    monkeypatch: pytest.MonkeyPatch, create: Callable[..., Answer]
) -> tuple[InstructorStructuredClient, dict[str, Any], list[dict[str, Any]]]:
    openai_calls: list[dict[str, Any]] = []

    def build_openai(**kwargs: Any) -> object:
        openai_calls.append(kwargs)
        return object()

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(client_module.openai, "OpenAI", build_openai)
    monkeypatch.setattr(client_module.instructor, "from_openai", lambda raw, *, mode: fake_client)
    return InstructorStructuredClient(openrouter_settings()), openai_calls[0], []


def complete(client: InstructorStructuredClient) -> Answer:
    return client.complete_structured(
        system="You are a test.",
        prompt="Answer the question.",
        response_model=Answer,
    )


class TestInstructorStructuredClient:
    def test_returns_the_instructor_validated_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        create_calls: list[dict[str, Any]] = []

        def create(**kwargs: Any) -> Answer:
            create_calls.append(kwargs)
            return Answer(value="42")

        client, _, _ = client_with_create(monkeypatch, create)

        assert complete(client) == Answer(value="42")
        assert create_calls == [
            {
                "model": "deepseek/deepseek-chat",
                "max_tokens": 256,
                "messages": [
                    {"role": "system", "content": "You are a test."},
                    {"role": "user", "content": "Answer the question."},
                ],
                "response_model": Answer,
                "max_retries": 0,
                "extra_body": {"provider": {"data_collection": "deny"}},
            }
        ]

    def test_maps_validation_failure_to_malformed_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def create(**kwargs: Any) -> Answer:
            raise ValidationError.from_exception_data(
                Answer.__name__,
                [{"type": "missing", "loc": ("value",), "input": {}}],
            )

        client, _, _ = client_with_create(monkeypatch, create)

        with pytest.raises(MalformedModelOutputError):
            complete(client)

    def test_maps_openai_failure_to_request_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def create(**kwargs: Any) -> Answer:
            raise openai.APIConnectionError(
                message="OpenRouter is unavailable.",
                request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            )

        client, _, _ = client_with_create(monkeypatch, create)

        with pytest.raises(LLMRequestError):
            complete(client)

    def test_maps_instructor_wrapped_openai_failure_to_request_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def create(**kwargs: Any) -> Answer:
            request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            provider_error = openai.APIStatusError(
                "OpenRouter is unavailable.",
                response=httpx.Response(503, request=request),
                body={"error": "Service unavailable."},
            )
            retry_error = InstructorRetryException(
                "Instructor request failed.",
                n_attempts=1,
                total_usage=0,
            )
            raise retry_error from provider_error

        client, _, _ = client_with_create(monkeypatch, create)

        with pytest.raises(LLMRequestError, match="HTTP 503"):
            complete(client)

    def test_uses_default_openrouter_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, openai_kwargs, _ = client_with_create(
            monkeypatch, lambda **kwargs: Answer(value="42")
        )

        assert client.description == "openrouter/deepseek/deepseek-chat"
        assert openai_kwargs["base_url"] == OPENROUTER_BASE_URL
        assert openai_kwargs["max_retries"] == 1

    def test_description_never_contains_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, _, _ = client_with_create(monkeypatch, lambda **kwargs: Answer(value="42"))

        assert "sk-or-test" not in client.description


class TestClientSelection:
    def test_none_provider_is_rejected(self) -> None:
        settings = Settings(_env_file=None, llm_provider=LLMProvider.NONE)  # type: ignore[call-arg]

        with pytest.raises(ConfigurationError):
            get_structured_client(settings)
