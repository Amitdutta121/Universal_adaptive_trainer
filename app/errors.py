"""Application error types and the FastAPI handlers that serialize them.

Every expected failure should be raised as an :class:`AdaptiveTrainerError`
subclass. Handlers registered by :func:`register_error_handlers` translate them
into JSON responses so browser and server clients see the same error contract.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AdaptiveTrainerError(Exception):
    """Base class for all expected application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ConfigurationError(AdaptiveTrainerError):
    """Configuration is missing or inconsistent (e.g. no LLM credentials)."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "configuration_error"


class NotFoundError(AdaptiveTrainerError):
    """A requested entity does not exist."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class DomainRuleError(AdaptiveTrainerError):
    """A domain invariant was violated (bad score range, unapproved curriculum, ...)."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "domain_rule_violation"


class UnsupportedFileError(AdaptiveTrainerError):
    """An uploaded file is of a type this system cannot read.

    Rejected before anything is stored, so an unreadable upload never becomes a
    book row that looks like it might work later.
    """

    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_file"


class FileTooLargeError(AdaptiveTrainerError):
    """An uploaded file exceeds the configured size limit."""

    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "file_too_large"


class InvalidBookDocumentError(AdaptiveTrainerError):
    """An uploaded book JSON document does not satisfy the schema.

    Rejected in full, before any row is written, with the offending fields named
    in ``detail`` so the document's producer can be corrected. A partially valid
    book is never partially imported.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_book_document"


class InvalidTaxonomyDocumentError(AdaptiveTrainerError):
    """An uploaded taxonomy JSON document does not satisfy the schema.

    Rejected in full, before any row is written, with the offending fields named
    in ``detail`` so the document's producer can be corrected.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_taxonomy_document"


class InvalidQuestionSpecError(AdaptiveTrainerError):
    """A generation QuestionSpec names ids that are missing or not approved."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_question_spec"


class LLMRequestError(AdaptiveTrainerError):
    """The LLM provider could not be reached, or refused the request.

    A transport or provider-side failure, as opposed to
    :class:`MalformedModelOutputError`, which means the call succeeded but the
    content that came back was unusable.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "llm_request_failed"


class MalformedModelOutputError(AdaptiveTrainerError):
    """A model returned output that does not satisfy the schema it was given.

    Raised rather than repaired. Guessing at what a malformed response "meant"
    would put invented curriculum structure in front of the professor with no
    way to tell it apart from analysis that actually succeeded.
    """

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "malformed_model_output"


class SchemaOutOfDateError(AdaptiveTrainerError):
    """The SQLite file predates the current ORM models.

    There is no migration tool yet (``docs/DECISIONS.md`` ADR-008), so this
    reports the mismatch and the remedy instead of letting SQLAlchemy fail later
    with a bare "no such column".
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "schema_out_of_date"


class FeatureNotAvailableError(AdaptiveTrainerError):
    """A module boundary exists but the feature behind it is not implemented yet.

    Used by the deferred subsystems (book extraction, LLM generation) so callers
    get an explicit, honest failure instead of a silent no-op.
    """

    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "feature_not_available"


class NoQuestionAvailableError(AdaptiveTrainerError):
    """The adaptive engine could not find a question to serve (ADR-041).

    Distinct from a domain rule violation: the request was valid and the engine
    worked correctly. The question set simply holds nothing for any subtopic it
    could draw, even after relaxing difficulty. The remedy is to write questions
    for the gap the coverage grid names, so this is reported as a state of the
    bank rather than as a bad request.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "no_question_available"


class ResourceInUseError(AdaptiveTrainerError):
    """Deleting this row would strand something that still points at it.

    Raised instead of deleting silently, so the professor sees what depends on
    the row before deciding. The caller may then repeat the request with an
    explicit override: refusing is the default, not the only answer.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "resource_in_use"


class UnoverridableConflictError(ResourceInUseError):
    """Deleting this row is refused, and no override exists.

    The distinction from its parent is the whole point. A plain
    :class:`ResourceInUseError` names a cost and invites the caller to repeat the
    request with ``force``; this one says there is nothing left to decide,
    because what depends on the row cannot be rebuilt or removed either. It
    carries its own code so a client can tell the two apart without reading the
    prose -- offering a "delete anyway" button that is guaranteed to fail is a
    worse answer than not offering one.

    A subclass so that ``except ResourceInUseError`` keeps catching both.
    """

    code = "conflict_not_overridable"


def register_error_handlers(app: FastAPI) -> None:
    """Attach the application's exception handlers to ``app``."""

    def _respond(*, status_code: int, code: str, message: str, detail: str | None) -> Response:
        body: dict[str, object] = {"error": {"code": code, "message": message}}
        if detail:
            body["error"]["detail"] = detail  # type: ignore[index]
        return JSONResponse(status_code=status_code, content=body)

    @app.exception_handler(AdaptiveTrainerError)
    async def _handle_app_error(request: Request, exc: AdaptiveTrainerError) -> Response:
        logger.warning(
            "%s on %s %s: %s", type(exc).__name__, request.method, request.url.path, exc.message
        )
        return _respond(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> Response:
        message = str(exc.detail) if exc.detail else "Request could not be completed."
        if exc.status_code >= 500:
            logger.error("HTTP %s on %s %s", exc.status_code, request.method, request.url.path)
        else:
            logger.info("HTTP %s on %s %s", exc.status_code, request.method, request.url.path)
        return _respond(
            status_code=exc.status_code,
            code=f"http_{exc.status_code}",
            message=message,
            detail=None,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
        logger.info("Invalid request on %s %s: %s", request.method, request.url.path, exc.errors())
        return _respond(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid_request",
            message="The submitted data was not valid.",
            detail=str(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> Response:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _respond(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="Something went wrong. Check the server log for details.",
            detail=None,
        )
