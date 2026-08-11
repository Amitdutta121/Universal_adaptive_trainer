"""The structured-output LLM client (Instructor over OpenRouter)."""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar

import instructor
import openai
from instructor.core import InstructorError
from pydantic import BaseModel, ValidationError

from app.config import LLMProvider, Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError, MalformedModelOutputError
from app.llm.availability import require_llm

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 1
ModelT = TypeVar("ModelT", bound=BaseModel)


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
    ) -> ModelT:
        """Return a validated response model instance."""
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

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
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
        self._client = instructor.from_openai(raw, mode=instructor.Mode.JSON)

    @property
    def description(self) -> str:
        """Return provenance for the configured OpenRouter route."""
        return f"{self.provider_label}/{self._settings.llm_model}"

    def complete_structured(
        self,
        *,
        system: str,
        prompt: str,
        response_model: type[ModelT],
    ) -> ModelT:
        """Return an Instructor-validated structured response without repair retries."""
        try:
            return self._client.chat.completions.create(
                model=self._settings.llm_model,
                max_tokens=self._settings.llm_max_output_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                response_model=response_model,
                max_retries=0,
                extra_body={"provider": {"data_collection": "deny"}},
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


def get_structured_client(settings: Settings | None = None) -> StructuredLLMClient:
    """Return the configured OpenRouter structured-output client."""
    settings = require_llm(settings or get_settings())
    if settings.llm_provider is LLMProvider.OPENROUTER:
        return InstructorStructuredClient(settings)
    raise ConfigurationError(
        f"No structured client exists for provider {settings.llm_provider.value!r}."
    )
