"""Tracing must be optional and must never be able to break the service."""

from __future__ import annotations

import pytest

from backend.runtime import tracing
from backend.runtime.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, log_level="WARNING", **overrides)  # type: ignore[arg-type, call-arg]


def test_tracing_is_a_noop_without_credentials() -> None:
    assert tracing.configure_tracing(_settings()) is False


def test_partial_credentials_do_not_enable_tracing() -> None:
    assert tracing.configure_tracing(_settings(langfuse_public_key="pk")) is False


def test_setup_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A broken Langfuse must degrade to "no tracing", not to a failed startup."""
    import langfuse

    def explode() -> object:
        raise RuntimeError("langfuse is unreachable")

    monkeypatch.setattr(langfuse, "get_client", explode)
    enabled = tracing.configure_tracing(
        _settings(langfuse_public_key="pk", langfuse_secret_key="sk")
    )
    assert enabled is False


def test_shutdown_is_safe_when_tracing_never_started() -> None:
    tracing.shutdown_tracing()
    tracing.shutdown_tracing()


class _FakeClient:
    def __init__(self) -> None:
        self.flushed = 0

    def flush(self) -> None:
        self.flushed += 1


def test_tracing_enables_and_flushes(monkeypatch: pytest.MonkeyPatch) -> None:
    import langfuse
    from pydantic_ai import Agent

    fake = _FakeClient()
    instrumented: list[bool] = []

    monkeypatch.setattr(langfuse, "get_client", lambda: fake)
    monkeypatch.setattr(Agent, "instrument_all", lambda: instrumented.append(True))
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    enabled = tracing.configure_tracing(
        _settings(
            langfuse_public_key="pk-live",
            langfuse_secret_key="sk-live",
            langfuse_host="https://lf.test",
        )
    )

    assert enabled is True
    assert instrumented == [True]
    import os

    assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk-live"
    assert os.environ["LANGFUSE_HOST"] == "https://lf.test"

    tracing.shutdown_tracing()
    assert fake.flushed == 1

    # Shutting down twice must not flush twice.
    tracing.shutdown_tracing()
    assert fake.flushed == 1


def test_flush_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    import langfuse
    from pydantic_ai import Agent

    class _ExplodingClient:
        def flush(self) -> None:
            raise RuntimeError("network gone")

    monkeypatch.setattr(langfuse, "get_client", lambda: _ExplodingClient())
    monkeypatch.setattr(Agent, "instrument_all", lambda: None)

    tracing.configure_tracing(_settings(langfuse_public_key="pk", langfuse_secret_key="sk"))
    tracing.shutdown_tracing()  # must not raise
