"""HTTP middleware: per-request logging with a correlation id."""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status and duration for every request.

    Attaches a request id to ``request.state`` and echoes it back in the
    response header so a log line can be tied to a specific browser action.
    Static asset requests are logged at DEBUG to keep the console readable.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:12]
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            # The exception handlers own the response; this logs the timing.
            logger.exception(
                "[%s] %s %s failed after %.1fms",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        level = logging.DEBUG if request.url.path.startswith("/static") else logging.INFO
        logger.log(
            level,
            "[%s] %s %s -> %d (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
