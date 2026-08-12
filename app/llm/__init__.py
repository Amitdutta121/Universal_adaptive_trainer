"""LLM provider boundary for Instructor-backed OpenRouter structured output.

Callers supply a Pydantic response model and receive a validated instance. This
package owns provider selection and configuration availability; it provides no
free-text completion API.

:mod:`app.llm.batch` adds a second, asynchronous transport for the same kind of
work (ADR-030). It is separate because a batch job is submitted now and
collected hours later, which no synchronous client can express. Both transports
take their prompts and response schema from the caller, so neither owns a
prompt of its own.
"""

from __future__ import annotations

from app.llm.availability import describe_availability, require_llm
from app.llm.batch import (
    BatchJobState,
    BatchRequestItem,
    BatchResultLine,
    build_custom_id,
    download_results,
    fetch_status,
    parse_custom_id,
    split_into_jobs,
    submit_batch,
)
from app.llm.client import StructuredLLMClient, get_structured_client

__all__ = [
    "BatchJobState",
    "BatchRequestItem",
    "BatchResultLine",
    "StructuredLLMClient",
    "build_custom_id",
    "describe_availability",
    "download_results",
    "fetch_status",
    "get_structured_client",
    "parse_custom_id",
    "require_llm",
    "split_into_jobs",
    "submit_batch",
]
