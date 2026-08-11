"""The structured-output LLM client.

The provider is faked at the HTTP boundary rather than above it, so what is under
test is the request this application actually sends and the way it reads what
comes back. Two failure modes must stay distinct: the provider failing, and the
provider succeeding with unusable content.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.config import LLMProvider, Settings
from app.errors import ConfigurationError, LLMRequestError, MalformedModelOutputError
from app.llm import get_structured_client
from app.llm.client import (
    AnthropicStructuredClient,
    OpenAIStructuredClient,
    OpenRouterStructuredClient,
    to_strict_schema,
)

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def anthropic_settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider=LLMProvider.ANTHROPIC,
        llm_model="claude-sonnet-5",
        llm_api_key="sk-test-secret",
        **overrides,
    )


def openai_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-test",
        llm_api_key="sk-test-secret",
    )


def openrouter_settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        llm_provider=LLMProvider.OPENROUTER,
        llm_model="deepseek/deepseek-chat",
        llm_api_key="sk-or-v1-test-secret",
        **overrides,
    )


class RecordingTransport:
    """Stands in for ``httpx.post``, capturing what was sent."""

    def __init__(self, *responses: httpx.Response) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, *, headers: dict[str, str], json: Any, timeout: float) -> Any:
        self.calls.append({"url": url, "headers": headers, "body": json, "timeout": timeout})
        response = self._responses.pop(0)
        if isinstance(response, Exception):  # pragma: no cover - defensive
            raise response
        return response


def response(status_code: int, payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://example.invalid/v1"),
    )


def call(client: Any) -> dict[str, Any]:
    return client.complete_structured(
        system="You are a test.",
        prompt="Answer the question.",
        schema_name="record_answer",
        schema_description="Record an answer.",
        json_schema=SCHEMA,
    )


class TestAnthropicClient:
    def test_a_tool_use_answer_is_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = RecordingTransport(
            response(
                200,
                {
                    "content": [
                        {"type": "text", "text": "Let me record that."},
                        {"type": "tool_use", "name": "record_answer", "input": {"answer": "42"}},
                    ],
                    "stop_reason": "tool_use",
                },
            )
        )
        monkeypatch.setattr(httpx, "post", transport)

        assert call(AnthropicStructuredClient(anthropic_settings())) == {"answer": "42"}

    def test_the_schema_is_sent_as_a_forced_tool(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Structured output only works if the model is *made* to use the tool."""
        transport = RecordingTransport(
            response(200, {"content": [{"type": "tool_use", "input": {"answer": "42"}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        call(AnthropicStructuredClient(anthropic_settings()))

        body = transport.calls[0]["body"]
        assert body["tools"][0]["input_schema"] == SCHEMA
        assert body["tool_choice"] == {"type": "tool", "name": "record_answer"}
        assert body["model"] == "claude-sonnet-5"

    def test_the_credential_travels_in_the_header_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = RecordingTransport(
            response(200, {"content": [{"type": "tool_use", "input": {"answer": "42"}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        call(AnthropicStructuredClient(anthropic_settings()))

        assert transport.calls[0]["headers"]["x-api-key"] == "sk-test-secret"
        assert "sk-test-secret" not in json.dumps(transport.calls[0]["body"])

    def test_an_answer_without_the_tool_call_is_malformed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            httpx,
            "post",
            RecordingTransport(
                response(
                    200,
                    {
                        "content": [{"type": "text", "text": "I'd rather not."}],
                        "stop_reason": "end_turn",
                    },
                )
            ),
        )
        with pytest.raises(MalformedModelOutputError):
            call(AnthropicStructuredClient(anthropic_settings()))

    def test_a_non_object_tool_input_is_malformed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "post",
            RecordingTransport(
                response(200, {"content": [{"type": "tool_use", "input": ["not", "an", "object"]}]})
            ),
        )
        with pytest.raises(MalformedModelOutputError):
            call(AnthropicStructuredClient(anthropic_settings()))


class TestOpenAIClient:
    def test_a_json_schema_answer_is_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "post",
            RecordingTransport(
                response(
                    200,
                    {"choices": [{"message": {"content": '{"answer": "42"}'}}]},
                )
            ),
        )
        assert call(OpenAIStructuredClient(openai_settings())) == {"answer": "42"}

    def test_the_schema_is_sent_in_strict_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = RecordingTransport(
            response(200, {"choices": [{"message": {"content": '{"answer": "42"}'}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        call(OpenAIStructuredClient(openai_settings()))

        response_format = transport.calls[0]["body"]["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        assert response_format["json_schema"]["schema"] == SCHEMA

    def test_content_that_is_not_json_is_malformed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "post",
            RecordingTransport(
                response(200, {"choices": [{"message": {"content": "Sorry, no."}}]})
            ),
        )
        with pytest.raises(MalformedModelOutputError):
            call(OpenAIStructuredClient(openai_settings()))

    def test_empty_content_is_malformed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "post",
            RecordingTransport(
                response(
                    200, {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
                )
            ),
        )
        with pytest.raises(MalformedModelOutputError) as caught:
            call(OpenAIStructuredClient(openai_settings()))
        assert "length" in (caught.value.detail or "")


class TestTransportFailures:
    def test_a_transient_status_is_retried_once_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = RecordingTransport(
            response(429, {"error": "slow down"}),
            response(200, {"content": [{"type": "tool_use", "input": {"answer": "42"}}]}),
        )
        monkeypatch.setattr(httpx, "post", transport)

        assert call(AnthropicStructuredClient(anthropic_settings())) == {"answer": "42"}
        assert len(transport.calls) == 2

    def test_a_persistent_transient_status_fails_as_a_request_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = RecordingTransport(
            response(503, {"error": "down"}), response(503, {"error": "down"})
        )
        monkeypatch.setattr(httpx, "post", transport)

        with pytest.raises(LLMRequestError):
            call(AnthropicStructuredClient(anthropic_settings()))
        assert len(transport.calls) == 2

    def test_a_client_error_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A rejected schema will be rejected again; retrying just costs money."""
        transport = RecordingTransport(response(400, {"error": "bad schema"}))
        monkeypatch.setattr(httpx, "post", transport)

        with pytest.raises(LLMRequestError):
            call(AnthropicStructuredClient(anthropic_settings()))
        assert len(transport.calls) == 1


class TestOpenRouterClient:
    """OpenRouter speaks OpenAI's wire format; only the routing differs."""

    def test_the_request_goes_to_openrouter_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = RecordingTransport(
            response(200, {"choices": [{"message": {"content": '{"answer": "42"}'}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        assert call(OpenRouterStructuredClient(openrouter_settings())) == {"answer": "42"}
        assert transport.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
        assert transport.calls[0]["body"]["model"] == "deepseek/deepseek-chat"

    def test_a_base_url_override_still_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        transport = RecordingTransport(
            response(200, {"choices": [{"message": {"content": '{"answer": "42"}'}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        call(OpenRouterStructuredClient(openrouter_settings(llm_base_url="https://proxy/v1")))
        assert transport.calls[0]["url"] == "https://proxy/v1/chat/completions"

    def test_routing_is_restricted_to_providers_that_honour_the_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without this, a route that ignores response_format returns prose."""
        transport = RecordingTransport(
            response(200, {"choices": [{"message": {"content": '{"answer": "42"}'}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        call(OpenRouterStructuredClient(openrouter_settings()))
        assert transport.calls[0]["body"]["provider"]["require_parameters"] is True
        assert transport.calls[0]["body"]["provider"]["data_collection"] == "deny"

    def test_the_credential_travels_in_the_header_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transport = RecordingTransport(
            response(200, {"choices": [{"message": {"content": '{"answer": "42"}'}}]})
        )
        monkeypatch.setattr(httpx, "post", transport)
        call(OpenRouterStructuredClient(openrouter_settings()))
        sent = transport.calls[0]
        assert sent["headers"]["authorization"] == "Bearer sk-or-v1-test-secret"
        assert "sk-or-v1-test-secret" not in json.dumps(sent["body"])

    def test_provenance_names_openrouter_not_openai(self) -> None:
        description = OpenRouterStructuredClient(openrouter_settings()).description
        assert description == "openrouter/deepseek/deepseek-chat"
        assert "sk-or-v1-test-secret" not in description


class TestStrictSchema:
    """Strict mode rejects a schema whose ``required`` misses a property."""

    def test_a_field_with_a_default_is_still_marked_required(self) -> None:
        from app.curriculum.schema import SectionAnalysis, json_schema_for

        generated = json_schema_for(SectionAnalysis)
        assert "concepts" not in generated["required"]

        strict = to_strict_schema(generated)
        assert set(strict["required"]) == set(strict["properties"])
        assert "concepts" in strict["required"]

    def test_nested_definitions_are_strictened_too(self) -> None:
        from app.curriculum.schema import NormalizationResult, json_schema_for

        strict = to_strict_schema(json_schema_for(NormalizationResult))
        group = strict["$defs"]["ConceptGroup"]
        assert set(group["required"]) == set(group["properties"])
        assert group["additionalProperties"] is False

    def test_the_original_schema_is_not_mutated(self) -> None:
        original = {"type": "object", "properties": {"a": {"type": "string"}}}
        to_strict_schema(original)
        assert "required" not in original

    def test_a_schema_without_properties_is_left_alone(self) -> None:
        assert to_strict_schema({"type": "string"}) == {"type": "string"}


class TestClientSelection:
    def test_the_provider_decides_the_client(self) -> None:
        assert isinstance(get_structured_client(anthropic_settings()), AnthropicStructuredClient)
        assert isinstance(get_structured_client(openai_settings()), OpenAIStructuredClient)
        assert isinstance(get_structured_client(openrouter_settings()), OpenRouterStructuredClient)

    def test_an_unconfigured_install_is_refused_before_any_call(self) -> None:
        settings = Settings(_env_file=None, llm_provider=LLMProvider.NONE)  # type: ignore[call-arg]
        with pytest.raises(ConfigurationError):
            get_structured_client(settings)

    def test_the_description_names_the_model_without_the_key(self) -> None:
        description = AnthropicStructuredClient(anthropic_settings()).description
        assert description == "anthropic/claude-sonnet-5"
        assert "sk-test-secret" not in description
