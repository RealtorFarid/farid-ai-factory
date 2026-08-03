"""Request-scoped context: correlation id and access logging."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.runtime.logger import bind_request_context, clear_request_context, get_logger

__all__ = ["RequestContextMiddleware", "get_request_id"]

log = get_logger("api.access")


def get_request_id(request: Request) -> str:
    """Return the correlation id for this request (``"-"`` if unavailable)."""
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else "-"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a correlation id, bind it to the logger, and log the access line.

    An inbound correlation id is honoured so a request can be traced across
    services; otherwise a UUID4 is generated.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = request_id

        clear_request_context()
        bind_request_context(request_id=request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers build the response; we only record timing.
            log.exception(
                "request.failed",
                method=request.method,
                path=request.url.path,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        finally:
            clear_request_context()

        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[self.header_name] = request_id
        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        return response
