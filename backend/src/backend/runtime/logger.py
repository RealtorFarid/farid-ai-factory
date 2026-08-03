"""Structured logging.

``print`` is not used anywhere in the runtime. Every log line goes through
structlog, which renders human-readable output in development and JSON in
production. Standard-library loggers (uvicorn, httpx, ...) are routed through
the same pipeline so output stays uniform.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars
from structlog.typing import Processor

from backend.runtime.config import LogFormat, LogLevel

__all__ = [
    "bind_request_context",
    "clear_request_context",
    "configure_logging",
    "get_logger",
]

_configured = False

# Loggers that install their own handlers; we strip those so the root handler
# (and therefore structlog) owns all formatting.
_HIJACKED_LOGGERS = ("uvicorn", "uvicorn.error")

# uvicorn.access is silenced rather than re-routed: RequestContextMiddleware
# already emits an access line, and its version carries the request id. Without
# this, configure_logging() would run after uvicorn's own setup and undo
# `access_log=False`, producing two lines per request.
_SILENCED_LOGGERS = ("uvicorn.access",)


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def configure_logging(level: LogLevel = "INFO", log_format: LogFormat = "console") -> None:
    """Configure structlog and the stdlib root logger. Safe to call repeatedly."""
    global _configured

    shared = _shared_processors()

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _HIJACKED_LOGGERS:
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers.clear()
        stdlib_logger.propagate = True

    for name in _SILENCED_LOGGERS:
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers.clear()
        stdlib_logger.propagate = False

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, configuring logging on first use if needed."""
    if not _configured:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


def bind_request_context(**values: Any) -> None:
    """Attach key/values to every log line emitted by the current task."""
    bind_contextvars(**values)


def clear_request_context() -> None:
    clear_contextvars()
