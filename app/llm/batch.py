"""Asynchronous batch transport for structured LLM work (ADR-030).

Why this is not the Instructor client
    :mod:`app.llm.client` completes one prompt and hands back a validated model
    instance. A batch job cannot do that: it is submitted now, runs for up to 24
    hours somewhere else, and is collected later by a separate request. There is
    no call to wrap, so the request bodies are built by hand here and the
    response is parsed by hand -- Instructor never sees either.

    The rubric is *not* rebuilt here. Callers pass the same system and user
    prompts the synchronous judge sends, plus the JSON schema of the same
    response model, so the two paths cannot drift into asking different
    questions.

Why it knows nothing about evaluation
    ``app.llm`` sits below the subsystems and must not import them, so this
    module takes prompts and a JSON schema as arguments rather than importing
    :mod:`app.evaluation`. It is a transport, not a judge.

Wire format
    OpenRouter's batch API lives under ``/api/beta``, not the ``/api/v1`` path
    the synchronous client uses, and it takes requests inline rather than as an
    uploaded JSONL file. One submission is::

        {"endpoint": ..., "model": ..., "requests": [{"custom_id", "body"}]}

    Those three keys must serialise in that order because the provider stream-
    parses the body and rejects it otherwise -- which is why this module dumps
    JSON itself and posts raw content instead of handing httpx a mapping.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import ConfigurationError, LLMRequestError

logger = logging.getLogger(__name__)

#: Separates the run from the question inside a provider ``custom_id``. A run id
#: is a UUID and a question id is an integer, so neither can contain it.
CUSTOM_ID_SEPARATOR = ":"

#: The chat-completions shape, selected per batch rather than per request.
BATCH_ENDPOINT = "/v1/chat/completions"

#: Provider lifecycle values that mean "still working". ``validating`` and
#: ``finalizing`` are distinct provider states but the same wait to a caller.
PENDING_PROVIDER_STATUSES = frozenset({"validating", "in_progress", "finalizing"})


def build_custom_id(run_id: str, question_id: int) -> str:
    """Return the id that ties one provider result back to one question."""
    return f"{run_id}{CUSTOM_ID_SEPARATOR}{question_id}"


def parse_custom_id(custom_id: str) -> tuple[str, int]:
    """Split a ``custom_id`` back into its run and question.

    Raises:
        ValueError: if the id is not one this module produced. Ingest treats
            that as a bad result line rather than guessing at a question.
    """
    run_id, separator, raw_question_id = custom_id.rpartition(CUSTOM_ID_SEPARATOR)
    if not separator or not run_id:
        raise ValueError(f"custom_id {custom_id!r} is not run_id{CUSTOM_ID_SEPARATOR}question_id")
    return run_id, int(raw_question_id)


@dataclass(frozen=True)
class BatchRequestItem:
    """One question's prompts, ready to become a request in a provider job."""

    custom_id: str
    system: str
    prompt: str


@dataclass(frozen=True)
class BatchResultLine:
    """One provider result, reduced to what ingest needs.

    Exactly one of ``content`` and ``error`` is set. A line the provider marked
    failed, and a line whose body did not carry assistant content, both arrive
    here as an ``error`` -- the difference does not change what ingest records.
    """

    custom_id: str
    content: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchJobState:
    """The provider's view of one submitted job."""

    batch_id: str
    status: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    error_detail: str | None = None
    raw_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_pending(self) -> bool:
        return self.status in PENDING_PROVIDER_STATUSES


def build_schema_instruction(response_schema: dict[str, Any]) -> str:
    """Return the system-message text that asks for one JSON schema's shape.

    This mirrors what Instructor's ``Mode.JSON`` puts in the system message on
    the synchronous path, and it is a transport concern rather than a second
    rubric: *what* to ask about comes from the caller's prompts, and only *how
    to shape the answer* is added here.
    """
    return (
        "\n\nRespond with a single JSON object and nothing else. It must match "
        "this JSON schema:\n\n"
        f"{json.dumps(response_schema, ensure_ascii=False, indent=2)}"
    )


def build_request_body(
    item: BatchRequestItem,
    *,
    response_schema: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    """Return the chat-completions body for one batched request.

    ``model`` is deliberately absent: the provider applies the batch-level model
    to every request, and a body that names a different one is rejected.

    **Why ``json_object`` and not a strict ``json_schema``.** Strict mode
    requires ``additionalProperties: false`` on every object and every property
    listed as required; a Pydantic ``model_json_schema()`` satisfies neither, so
    passing one with ``strict: true`` gets the whole batch rejected upstream at
    validation. Rewriting the schema to suit one provider's strict dialect is
    exactly the wire-format maintenance ADR-020 removed, so this asks for
    ``json_object`` and states the schema in the system message -- byte for byte
    the approach Instructor takes on the synchronous path, which is known to
    work against this model. An answer that still does not fit becomes an
    ``error`` evaluation for that one question at ingest.

    ``provider.data_collection: deny`` is sent here for the same reason the
    synchronous client sends it (ADR-020) -- a batched request is still a
    request, and the routing preference should not lapse because the transport
    changed.
    """
    return {
        "messages": [
            {"role": "system", "content": item.system + build_schema_instruction(response_schema)},
            {"role": "user", "content": item.prompt},
        ],
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
        "provider": {"data_collection": "deny"},
    }


def build_batch_payload(
    items: Sequence[BatchRequestItem],
    *,
    model: str,
    response_schema: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    """Return one provider job body, with its keys in the required order."""
    return {
        "endpoint": BATCH_ENDPOINT,
        "model": model,
        "requests": [
            {
                "custom_id": item.custom_id,
                "body": build_request_body(
                    item,
                    response_schema=response_schema,
                    max_output_tokens=max_output_tokens,
                ),
            }
            for item in items
        ],
    }


def split_into_jobs(
    items: Sequence[BatchRequestItem], *, max_per_job: int
) -> Iterator[list[BatchRequestItem]]:
    """Chunk requests into provider-sized jobs.

    A bank larger than the cap becomes several jobs that share one run id, so
    the professor still sees one re-run rather than a number of them they would
    have to reconcile by hand.
    """
    if max_per_job < 1:
        raise ValueError("max_per_job must be at least 1")
    for start in range(0, len(items), max_per_job):
        yield list(items[start : start + max_per_job])


def _credential(settings: Settings) -> str:
    key = settings.judge_batch_credential
    if key is None:
        raise ConfigurationError(
            "The bulk judge re-run needs an API key.",
            detail="Set JUDGE_BATCH_API_KEY, or LLM_API_KEY, in your .env file.",
        )
    return key.get_secret_value()


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_credential(settings)}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost/adaptive-trainer",
        "X-Title": "Adaptive Trainer",
    }


def _request_error(exc: Exception, action: str) -> LLMRequestError:
    return LLMRequestError(
        f"Could not {action} the judge batch job.",
        detail=f"{type(exc).__name__}: {str(exc)[:400]}",
    )


def _bounded(text: str) -> str:
    return " ".join(text.split())[:400]


def submit_batch(
    items: Sequence[BatchRequestItem],
    *,
    response_schema: dict[str, Any],
    settings: Settings | None = None,
) -> str:
    """Submit one provider job and return its id.

    Raises:
        LLMRequestError: if the provider could not be reached or refused the
            submission. Nothing is recorded against the run in that case, so a
            rejected submission cannot leave a run that will never complete.
    """
    settings = settings or get_settings()
    payload = build_batch_payload(
        items,
        model=settings.judge_batch_route,
        response_schema=response_schema,
        max_output_tokens=settings.llm_max_output_tokens,
    )
    # Serialised here rather than passed to httpx as a mapping so the documented
    # endpoint/model/requests key order is guaranteed by this module.
    body = json.dumps(payload, ensure_ascii=False)
    try:
        response = httpx.post(
            f"{settings.judge_batch_base_url.rstrip('/')}/batches",
            content=body.encode("utf-8"),
            headers=_headers(settings),
            timeout=settings.judge_batch_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise _request_error(exc, "submit") from exc

    if response.status_code >= 400:
        raise LLMRequestError(
            f"The batch provider returned HTTP {response.status_code}.",
            detail=_bounded(response.text) or "The provider sent an empty response body.",
        )
    try:
        batch_id = response.json()["id"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMRequestError(
            "The batch provider accepted the job without returning an id.",
            detail=_bounded(response.text),
        ) from exc
    logger.info("Submitted judge batch job %s with %d requests", batch_id, len(items))
    return str(batch_id)


def fetch_status(batch_id: str, *, settings: Settings | None = None) -> BatchJobState:
    """Return the provider's current state for one job.

    A completed job carries its results inline, so this also populates
    ``raw_results``; :func:`download_results` reads them out of the same body
    rather than issuing a second request the provider does not offer.
    """
    settings = settings or get_settings()
    try:
        response = httpx.get(
            f"{settings.judge_batch_base_url.rstrip('/')}/batches/{batch_id}",
            headers=_headers(settings),
            timeout=settings.judge_batch_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise _request_error(exc, "poll") from exc

    if response.status_code >= 400:
        raise LLMRequestError(
            f"The batch provider returned HTTP {response.status_code}.",
            detail=_bounded(response.text) or "The provider sent an empty response body.",
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise LLMRequestError(
            "The batch provider returned a status that is not JSON.",
            detail=_bounded(response.text),
        ) from exc
    return state_from_payload(batch_id, payload)


def state_from_payload(batch_id: str, payload: object) -> BatchJobState:
    """Reduce a provider status body to :class:`BatchJobState`.

    Tolerant on purpose: an absent ``request_counts`` or ``results`` means the
    job has not reached that stage, not that the response is unusable.
    """
    if not isinstance(payload, dict):
        return BatchJobState(batch_id=batch_id, status="failed", error_detail="Malformed status.")
    counts = payload.get("request_counts")
    counts = counts if isinstance(counts, dict) else {}
    results = payload.get("results")
    error = payload.get("error")
    return BatchJobState(
        batch_id=str(payload.get("id") or batch_id),
        status=str(payload.get("status") or "failed"),
        total=int(counts.get("total") or 0),
        completed=int(counts.get("completed") or 0),
        failed=int(counts.get("failed") or 0),
        error_detail=_bounded(json.dumps(error, ensure_ascii=False)) if error else None,
        raw_results=[item for item in results if isinstance(item, dict)]
        if isinstance(results, list)
        else [],
    )


def download_results(batch_id: str, *, settings: Settings | None = None) -> list[BatchResultLine]:
    """Return the finished lines of one job, in provider order."""
    return parse_results(fetch_status(batch_id, settings=settings).raw_results)


def parse_results(raw_results: Sequence[dict[str, Any]]) -> list[BatchResultLine]:
    """Turn provider result objects into result lines.

    A line missing its ``custom_id`` is dropped with a warning: there is nothing
    to attribute it to, and inventing an attribution would file one question's
    evaluation against another.
    """
    lines: list[BatchResultLine] = []
    for item in raw_results:
        custom_id = item.get("custom_id")
        if not isinstance(custom_id, str) or not custom_id:
            logger.warning("Dropping a batch result line with no custom_id")
            continue
        lines.append(_result_line(custom_id, item))
    return lines


def _result_line(custom_id: str, item: dict[str, Any]) -> BatchResultLine:
    if item.get("error"):
        return BatchResultLine(
            custom_id=custom_id,
            error=_bounded(json.dumps(item["error"], ensure_ascii=False)),
        )
    response = item.get("response")
    if not isinstance(response, dict):
        return BatchResultLine(custom_id=custom_id, error="The result carried no response.")

    status_code = response.get("status_code")
    if isinstance(status_code, int) and status_code >= 400:
        return BatchResultLine(
            custom_id=custom_id, error=f"The provider returned HTTP {status_code}."
        )

    content = _assistant_content(response.get("body"))
    if content is None:
        return BatchResultLine(
            custom_id=custom_id, error="The result carried no assistant content."
        )
    return BatchResultLine(custom_id=custom_id, content=content)


def _assistant_content(body: object) -> str | None:
    """Pull the assistant message text out of a chat-completion body."""
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) and content.strip() else None
