"""A single error envelope for every failure mode.

Every non-2xx response has the shape::

    {"error": {"code": ..., "message": ..., "request_id": ..., "details": ...}}

Unhandled exceptions are logged with a stack trace and reported as a generic
``internal_error`` — internals are never leaked to the caller.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.middleware import get_request_id
from backend.runtime.agent import AgentNotFoundError
from backend.runtime.logger import get_logger
from backend.runtime.orchestrator import RunNotResumableError, UnknownApprovalError
from backend.runtime.runner import AgentTimeoutError, PromptTooLongError
from backend.runtime.runs import RunNotFoundError

__all__ = ["error_response", "register_exception_handlers"]

log = get_logger(__name__)

# HTTP status -> stable machine-readable error code.
_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "internal_error",
    status.HTTP_504_GATEWAY_TIMEOUT: "timeout",
}


def error_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    code: str | None = None,
    details: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build the canonical error payload."""
    body: dict[str, Any] = {
        "code": code or _STATUS_CODES.get(status_code, "error"),
        "message": message,
        "request_id": get_request_id(request),
    }
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body})


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers for every exception type the API can surface."""

    @app.exception_handler(AgentNotFoundError)
    async def _agent_not_found(request: Request, exc: AgentNotFoundError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="agent_not_found",
            message=f"No agent named {exc.name!r}.",
        )

    @app.exception_handler(RunNotFoundError)
    async def _run_not_found(request: Request, exc: RunNotFoundError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            code="run_not_found",
            message=f"No run with id {exc.run_id!r}.",
        )

    @app.exception_handler(RunNotResumableError)
    async def _run_not_resumable(request: Request, exc: RunNotResumableError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_409_CONFLICT,
            code="run_not_resumable",
            message=str(exc),
        )

    @app.exception_handler(UnknownApprovalError)
    async def _unknown_approval(request: Request, exc: UnknownApprovalError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="unknown_approval",
            message=str(exc),
        )

    @app.exception_handler(PromptTooLongError)
    async def _prompt_too_long(request: Request, exc: PromptTooLongError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="prompt_too_long",
            message=str(exc),
        )

    @app.exception_handler(AgentTimeoutError)
    async def _agent_timeout(request: Request, exc: AgentTimeoutError) -> JSONResponse:
        return error_response(
            request,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="agent_timeout",
            message=str(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "location": list(err.get("loc", ())),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="Request validation failed.",
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            request,
            status_code=exc.status_code,
            message=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "request.unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="An internal error occurred.",
        )
