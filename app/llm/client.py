"""The structured-output LLM client (Instructor over OpenRouter)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Literal, Protocol, TypeVar

import instructor
import openai
from instructor.core import InstructorError
from pydantic import BaseModel, ValidationError

from app.config import LLMProvider, Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError, MalformedModelOutputError
from app.llm.availability import require_llm

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
#: Reasoning models (OpenAI's gpt-5 family and o-series) reject ``max_tokens`` and a
#: non-default ``temperature``; their hidden reasoning also spends the output budget.
_REASONING_MODEL = re.compile(r"^(gpt-5|o\d)", re.IGNORECASE)
#: Output budget for a reasoning model: the answer plus its reasoning tokens.
REASONING_OUTPUT_TOKENS = 16_000


def is_openrouter(settings: Settings) -> bool:
    """Whether calls go to OpenRouter (the default) rather than another OpenAI-style API."""
    return not settings.llm_base_url or "openrouter.ai" in settings.llm_base_url


def is_reasoning_model(model: str) -> bool:
    """``gpt-5-mini``, ``openai/o4-mini``: the deployment or route name of a reasoning model."""
    return bool(_REASONING_MODEL.match(model.rsplit("/", 1)[-1]))


MAX_RETRIES = 1
ModelT = TypeVar("ModelT", bound=BaseModel)

#: One earlier message of a conversation: who sent it, and its text. ``user`` is what the
#: application asked; ``assistant`` is what the model answered (rendered back as text).
ChatTurn = tuple[Literal["user", "assistant"], str]


class StructuredLLMClient(Protocol):
    """Completes a prompt as an instance of the requested Pydantic model."""

    @property
    def description(self) -> str:
        """Provider and model provenance, without credentials."""
        ...

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[ModelT],
        history: Sequence[ChatTurn] = (),
    ) -> ModelT:
        """Return a validated response model instance.

        ``history`` is the conversation before ``prompt``, oldest first: a retry sends the
        first request and the model's rejected answer, so the correction can refer to it.
        """
        ...


def _as_request_error(exc: openai.OpenAIError) -> LLMRequestError:
    """Convert an OpenAI-compatible SDK failure to an application request error."""
    status = getattr(exc, "status_code", None)
    detail = str(getattr(exc, "message", None) or exc)[:400]
    if status is not None:
        return LLMRequestError(
            f"The LLM provider returned HTTP {status}.",
            detail=detail or "The provider sent an empty response body.",
        )
    return LLMRequestError(
        "Could not reach the OpenRouter API.",
        detail=f"{type(exc).__name__}: {detail}",
    )


def _find_wrapped_openai_error(exc: BaseException) -> openai.OpenAIError | None:
    """Return an SDK failure preserved by an Instructor exception, if any."""
    pending = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, openai.OpenAIError):
            return current
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        failed_attempts = getattr(current, "failed_attempts", None)
        if failed_attempts:
            pending.extend(attempt.exception for attempt in failed_attempts)
    return None


def _malformed_output_detail(exc: BaseException) -> str:
    """Return the most useful bounded detail from a structured-output failure."""
    failed_attempts = getattr(exc, "failed_attempts", None)
    if failed_attempts:
        last_exception = failed_attempts[-1].exception
        return f"{type(last_exception).__name__}: {str(last_exception)[:400]}"
    return f"{type(exc).__name__}: {str(exc)[:400]}"


class InstructorStructuredClient:
    """Structured Pydantic completion through Instructor and OpenRouter."""

    provider_label = "openrouter"

    def __init__(
        self,
        settings: Settings,
        *,
        temperature: float | None = None,
        mode: instructor.Mode = instructor.Mode.JSON,
    ) -> None:
        self._settings = settings
        #: ``None`` leaves the provider default. Judges pass 0.0 so that a
        #: verdict is a measurement rather than a sample.
        self._temperature = temperature
        key = settings.llm_api_key
        if key is None:  # pragma: no cover - get_structured_client checks first
            raise ConfigurationError("No LLM API key is configured.")

        raw = openai.OpenAI(
            api_key=key.get_secret_value(),
            base_url=settings.llm_base_url or OPENROUTER_BASE_URL,
            timeout=settings.llm_timeout_seconds,
            max_retries=MAX_RETRIES,
            default_headers={
                "HTTP-Referer": "https://localhost/adaptive-trainer",
                "X-Title": "Adaptive Trainer",
            },
        )
        #: ``MD_JSON`` for models that wrap their JSON in a code fence (Claude Haiku does).
        self._client = instructor.from_openai(raw, mode=mode)

    @property
    def description(self) -> str:
        """Return provenance for the configured route."""
        label = self.provider_label if is_openrouter(self._settings) else "azure"
        return f"{label}/{self._settings.llm_model}"

    def _request_options(self) -> dict[str, object]:
        """Token limit, sampling and provider fields this route and model accept."""
        options: dict[str, object] = {}
        if is_reasoning_model(self._settings.llm_model):
            # Temperature stays at the model default: these models reject anything else.
            options["max_completion_tokens"] = max(
                self._settings.llm_max_output_tokens, REASONING_OUTPUT_TOKENS
            )
            options["reasoning_effort"] = self._settings.llm_reasoning_effort
        else:
            options["max_tokens"] = self._settings.llm_max_output_tokens
            if self._temperature is not None:
                options["temperature"] = self._temperature
        if is_openrouter(self._settings):
            options["extra_body"] = {"provider": {"data_collection": "deny"}}
        return options

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[ModelT],
        history: Sequence[ChatTurn] = (),
    ) -> ModelT:
        """Return an Instructor-validated structured response without repair retries."""
        try:
            return self._client.chat.completions.create(
                model=self._settings.llm_model,
                **self._request_options(),
                messages=[
                    {"role": "system", "content": system},
                    *({"role": role, "content": text} for role, text in history),
                    {"role": "user", "content": prompt},
                ],
                response_model=response_model,
                max_retries=0,
            )
        except openai.OpenAIError as exc:
            raise _as_request_error(exc) from exc
        except (InstructorError, ValidationError) as exc:
            if provider_error := _find_wrapped_openai_error(exc):
                raise _as_request_error(provider_error) from exc
            raise MalformedModelOutputError(
                "The model did not return a usable structured answer.",
                detail=_malformed_output_detail(exc),
            ) from exc


def get_structured_client(
    settings: Settings | None = None, *, temperature: float | None = None
) -> StructuredLLMClient:
    """Return the configured OpenRouter structured-output client.

    ``temperature`` is passed by callers that need a repeatable answer rather
    than a creative one -- the judges. Left ``None`` elsewhere, so generation
    keeps the provider default and stays diverse.
    """
    settings = require_llm(settings or get_settings())
    if settings.llm_provider is LLMProvider.OPENROUTER:
        return InstructorStructuredClient(settings, temperature=temperature)
    raise ConfigurationError(
        f"No structured client exists for provider {settings.llm_provider.value!r}."
    )
