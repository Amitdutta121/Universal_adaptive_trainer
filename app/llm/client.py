"""The structured-output LLM client.

Every LLM call in this application is a *structured* call: the caller supplies a
JSON Schema and receives a dictionary that satisfied it, or an error. There is no
free-text completion API here, and deliberately so -- the curriculum pipeline
parses model output into strict Pydantic models, and a text endpoint would invite
someone to pattern-match prose instead.

Provider SDKs rather than hand-rolled HTTP
    The official ``openai`` and ``anthropic`` clients own the transport:
    connection reuse, timeouts, retry with backoff, and the request shape each
    provider actually expects. Maintaining those by hand meant re-deriving
    details the vendors already encode -- and getting them wrong is silent, not
    loud. See ``docs/DECISIONS.md`` ADR-020, which supersedes ADR-017 on this
    point.

    OpenRouter speaks OpenAI's wire format, so it is reached through the
    ``openai`` client pointed at a different base URL, with its routing
    preferences carried in ``extra_body``.

Two failure modes, kept distinct
    :class:`~app.errors.LLMRequestError` means the provider could not be reached
    or refused the call. :class:`~app.errors.MalformedModelOutputError` means the
    call succeeded and the content is unusable. The distinction matters: the
    first is worth retrying, the second is not.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import anthropic
import openai

from app.config import LLMProvider, Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError, MalformedModelOutputError
from app.llm.availability import require_llm

logger = logging.getLogger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

#: One retry, matching the previous hand-rolled behaviour. The SDKs already
#: restrict retries to transport failures and 408/409/429/5xx, and back off
#: between attempts; a 4xx from a rejected schema is not retried, since it would
#: be rejected again at twice the cost.
MAX_RETRIES = 1


class StructuredLLMClient(Protocol):
    """Returns a JSON object satisfying a caller-supplied schema."""

    @property
    def description(self) -> str:
        """Provider and model, for provenance. Never includes the credential."""
        ...

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema_name: str,
        schema_description: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the model's structured answer as a plain dictionary.

        Raises:
            LLMRequestError: the provider could not be reached or refused.
            MalformedModelOutputError: the response carried no usable JSON object.
        """
        ...


def to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return ``schema`` in the form strict JSON-Schema modes insist on.

    OpenAI-compatible ``strict`` mode rejects an object schema whose ``required``
    array does not name *every* property. Pydantic omits a field that has a
    default -- ``SectionAnalysis.concepts`` is the one that matters here -- so the
    schema this application generates is refused with an HTTP 400 before the
    model ever sees it.

    Listing every property as required does not change what the application
    accepts: the model must now answer ``"concepts": []`` explicitly instead of
    leaving the key out, and :func:`~app.curriculum.schema.parse_structured`
    remains the authority on every other constraint. Nothing is relaxed, and the
    original schema object is left untouched.
    """
    if not isinstance(schema, dict):  # pragma: no cover - defensive
        return schema

    strict: dict[str, Any] = {}
    for key, value in schema.items():
        if key in ("properties", "$defs", "definitions") and isinstance(value, dict):
            strict[key] = {name: to_strict_schema(item) for name, item in value.items()}
        elif key == "items":
            strict[key] = to_strict_schema(value) if isinstance(value, dict) else value
        elif key in ("anyOf", "oneOf", "allOf") and isinstance(value, list):
            strict[key] = [to_strict_schema(item) for item in value]
        else:
            strict[key] = value

    properties = strict.get("properties")
    if isinstance(properties, dict):
        strict["required"] = list(properties)
        strict.setdefault("additionalProperties", False)
    return strict


def _require_object(value: Any, *, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MalformedModelOutputError(
            "The model did not return a JSON object.",
            detail=f"Found {type(value).__name__} in {where}.",
        )
    return value


def _as_request_error(exc: Exception, *, provider: str) -> LLMRequestError:
    """Convert an SDK exception into this application's transport error.

    Both SDKs put the provider's response body on the exception and the
    credential only in the request headers, so nothing sensitive can reach a log
    line or the professor's error page through here.
    """
    status = getattr(exc, "status_code", None)
    detail = str(getattr(exc, "message", None) or exc)[:400]
    if status is not None:
        return LLMRequestError(
            f"The LLM provider returned HTTP {status}.",
            detail=detail or "The provider sent an empty response body.",
        )
    return LLMRequestError(
        f"Could not reach the {provider} API.", detail=f"{type(exc).__name__}: {detail}"
    )


class AnthropicStructuredClient:
    """Anthropic Messages API, with a forced tool call carrying the schema.

    A tool whose ``input_schema`` is the caller's schema, plus ``tool_choice``
    naming that tool, is Anthropic's structured-output mechanism: the model must
    answer by calling it, so the answer arrives as validated JSON rather than as
    prose that happens to contain some.
    """

    provider_label = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        key = settings.llm_api_key
        if key is None:  # pragma: no cover - get_structured_client checks first
            raise ConfigurationError("No LLM API key is configured.")
        self._client = anthropic.Anthropic(
            api_key=key.get_secret_value(),
            base_url=settings.llm_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=MAX_RETRIES,
        )

    @property
    def description(self) -> str:
        return f"{self.provider_label}/{self._settings.llm_model}"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema_name: str,
        schema_description: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            message = self._client.messages.create(
                model=self._settings.llm_model,
                max_tokens=self._settings.llm_max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[
                    {
                        "name": schema_name,
                        "description": schema_description,
                        "input_schema": json_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": schema_name},
            )
        except anthropic.AnthropicError as exc:
            raise _as_request_error(exc, provider="Anthropic") from exc

        for block in message.content:
            if getattr(block, "type", None) == "tool_use":
                return _require_object(block.input, where="the tool call input")
        raise MalformedModelOutputError(
            "The model answered without calling the requested tool.",
            detail=f"stop_reason={message.stop_reason!r}, expected tool {schema_name!r}.",
        )


class OpenAICompatibleClient:
    """Chat completions with a strict ``json_schema`` response format.

    Shared by every provider that speaks OpenAI's wire format. Subclasses supply
    the default endpoint, the provenance string and any provider-specific headers
    or body fields; the request and the reading of the reply are identical, and
    keeping them in one place is what stops the two providers drifting apart.
    """

    #: Used when ``LLM_BASE_URL`` is not set.
    default_base_url: str = OPENAI_BASE_URL
    #: Prefix of :attr:`description`, so provenance names the service that was
    #: billed rather than the wire format it happened to speak.
    provider_label: str = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        key = settings.llm_api_key
        if key is None:  # pragma: no cover - get_structured_client checks first
            raise ConfigurationError("No LLM API key is configured.")
        self._client = openai.OpenAI(
            api_key=key.get_secret_value(),
            base_url=settings.llm_base_url or self.default_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=MAX_RETRIES,
            default_headers=self._extra_headers() or None,
        )

    @property
    def description(self) -> str:
        return f"{self.provider_label}/{self._settings.llm_model}"

    def _extra_headers(self) -> dict[str, str]:
        """Provider-specific headers. Never credentials."""
        return {}

    def _extra_body(self) -> dict[str, Any]:
        """Provider-specific request fields the OpenAI schema does not define."""
        return {}

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        schema_name: str,
        schema_description: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            completion = self._client.chat.completions.create(
                model=self._settings.llm_model,
                max_completion_tokens=self._settings.llm_max_output_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "description": schema_description,
                        "schema": to_strict_schema(json_schema),
                        "strict": True,
                    },
                },
                extra_body=self._extra_body() or None,
            )
        except openai.OpenAIError as exc:
            raise _as_request_error(exc, provider=self.provider_label) from exc

        if not completion.choices:
            raise MalformedModelOutputError(
                "The model returned no completion.", detail="The choices array was empty."
            )
        choice = completion.choices[0]
        content = choice.message.content
        if not isinstance(content, str) or not content.strip():
            raise MalformedModelOutputError(
                "The model returned empty content.",
                detail=f"finish_reason={choice.finish_reason!r}.",
            )
        try:
            return _require_object(json.loads(content), where="the message content")
        except json.JSONDecodeError as exc:
            raise MalformedModelOutputError(
                "The model's content was not valid JSON.",
                detail=f"{exc.msg} at line {exc.lineno}, column {exc.colno}.",
            ) from exc


class OpenAIStructuredClient(OpenAICompatibleClient):
    """OpenAI chat completions with a strict ``json_schema`` response format."""


class OpenRouterStructuredClient(OpenAICompatibleClient):
    """OpenRouter, used here to reach DeepSeek and other non-first-party models.

    OpenRouter routes one model name to whichever upstream provider is available.
    ``data_collection: deny`` keeps a professor's textbook content away from
    upstreams that retain prompts for training, which is the conservative default
    for the input this application handles.

    Not set: ``require_parameters``. It looks like the right guard -- route only
    to upstreams that honour ``response_format`` -- but no DeepSeek endpoint
    currently *advertises* structured output in its parameter list, so requiring
    it eliminates every route and the call fails with HTTP 404. The endpoints
    that serve these requests do honour the schema in practice; a route that ever
    stopped doing so surfaces as ``MalformedModelOutputError`` rather than as
    accepted nonsense.
    """

    default_base_url = OPENROUTER_BASE_URL
    provider_label = "openrouter"

    def _extra_headers(self) -> dict[str, str]:
        return {
            "HTTP-Referer": "https://localhost/adaptive-trainer",
            "X-Title": "Adaptive Trainer",
        }

    def _extra_body(self) -> dict[str, Any]:
        return {"provider": {"data_collection": "deny"}}


def get_structured_client(settings: Settings | None = None) -> StructuredLLMClient:
    """Return the configured structured client.

    Raises:
        ConfigurationError: if no provider or no credentials are configured. The
            caller gets an actionable message rather than a client that fails
            later, mid-run, with half a curriculum analysed.
    """
    settings = require_llm(settings or get_settings())
    if settings.llm_provider is LLMProvider.ANTHROPIC:
        return AnthropicStructuredClient(settings)
    if settings.llm_provider is LLMProvider.OPENAI:
        return OpenAIStructuredClient(settings)
    if settings.llm_provider is LLMProvider.OPENROUTER:
        return OpenRouterStructuredClient(settings)
    raise ConfigurationError(  # pragma: no cover - require_llm rejects NONE first
        f"No structured client exists for provider {settings.llm_provider.value!r}."
    )
