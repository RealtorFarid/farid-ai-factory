"""Logging configuration and request-scoped context binding."""

from __future__ import annotations

import json
import logging

import structlog

from backend.runtime.logger import (
    bind_request_context,
    clear_request_context,
    configure_logging,
    get_logger,
)


def test_json_format_emits_parseable_lines(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(level="INFO", log_format="json")
    get_logger("test").info("event.happened", answer=42)

    line = capsys.readouterr().err.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "event.happened"
    assert payload["answer"] == 42
    assert payload["level"] == "info"
    assert payload["timestamp"]


def test_context_vars_are_merged_into_every_line(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(level="INFO", log_format="json")
    clear_request_context()
    bind_request_context(request_id="abc-123")
    try:
        get_logger("test").info("with.context")
    finally:
        clear_request_context()

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["request_id"] == "abc-123"


def test_context_is_cleared(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(level="INFO", log_format="json")
    bind_request_context(request_id="abc-123")
    clear_request_context()
    get_logger("test").info("without.context")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert "request_id" not in payload


def test_stdlib_loggers_are_routed_through_structlog(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(level="INFO", log_format="json")
    logging.getLogger("uvicorn.error").info("from stdlib")

    payload = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert payload["event"] == "from stdlib"
    assert payload["logger"] == "uvicorn.error"


def test_uvicorn_access_logger_is_silenced(capsys) -> None:  # type: ignore[no-untyped-def]
    """The middleware emits the access line; uvicorn's duplicate must not appear."""
    configure_logging(level="INFO", log_format="json")
    logging.getLogger("uvicorn.access").info('GET /health HTTP/1.1" 200')

    assert capsys.readouterr().err.strip() == ""


def test_level_filtering_is_applied(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(level="WARNING", log_format="json")
    log = get_logger("test")
    log.info("suppressed")
    log.warning("emitted")

    lines = [line for line in capsys.readouterr().err.strip().splitlines() if line]
    assert len(lines) == 1
    assert json.loads(lines[0])["event"] == "emitted"


def test_configure_logging_is_idempotent() -> None:
    configure_logging(level="INFO", log_format="json")
    configure_logging(level="INFO", log_format="json")
    assert len(logging.getLogger().handlers) == 1
    structlog.reset_defaults()
