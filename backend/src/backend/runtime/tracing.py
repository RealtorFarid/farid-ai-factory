"""Observability: OpenTelemetry-based tracing exported to Langfuse.

Tracing is optional. When Langfuse credentials are absent the module degrades
to a no-op so local development and CI never depend on a network service.
A tracing failure must never take the API down.
"""

from __future__ import annotations

import os

from backend.runtime.config import Settings
from backend.runtime.logger import get_logger

__all__ = ["configure_tracing", "shutdown_tracing"]

log = get_logger(__name__)

_client: object | None = None


def configure_tracing(settings: Settings) -> bool:
    """Wire agent instrumentation to Langfuse.

    Returns ``True`` when tracing is active. Never raises.
    """
    global _client

    if not settings.tracing_enabled:
        log.info("tracing.disabled", reason="langfuse credentials not configured")
        return False

    try:
        # The Langfuse SDK reads credentials from the environment.
        assert settings.langfuse_public_key is not None
        assert settings.langfuse_secret_key is not None
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key.get_secret_value()
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key.get_secret_value()
        os.environ["LANGFUSE_HOST"] = settings.langfuse_host

        from langfuse import get_client  # imported lazily: optional dependency path
        from pydantic_ai import Agent

        _client = get_client()
        Agent.instrument_all()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("tracing.setup_failed", error=str(exc), exc_info=True)
        _client = None
        return False

    log.info("tracing.enabled", host=settings.langfuse_host)
    return True


def shutdown_tracing() -> None:
    """Flush buffered spans on shutdown. Never raises."""
    global _client

    if _client is None:
        return
    try:
        flush = getattr(_client, "flush", None)
        if callable(flush):
            flush()
            log.info("tracing.flushed")
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("tracing.flush_failed", error=str(exc))
    finally:
        _client = None
