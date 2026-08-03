"""The three process entry points: ASGI app, ``propilot`` CLI, smoke script."""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi import FastAPI

from backend.runtime.config import get_settings


@pytest.fixture(autouse=True)
def _clean_settings_cache() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_asgi_module_exposes_an_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPILOT_LOG_LEVEL", "WARNING")
    import backend.asgi

    module = importlib.reload(backend.asgi)
    assert isinstance(module.app, FastAPI)


def test_cli_starts_uvicorn_with_configured_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROPILOT_HOST", "0.0.0.0")
    monkeypatch.setenv("PROPILOT_PORT", "9999")
    monkeypatch.setenv("PROPILOT_LOG_LEVEL", "WARNING")

    from backend import cli

    captured: dict[str, Any] = {}

    def fake_run(target: str, **kwargs: Any) -> None:
        captured["target"] = target
        captured.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    cli.main()

    assert captured["target"] == "backend.asgi:app"
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9999
    # Logging is owned by structlog, not uvicorn.
    assert captured["log_config"] is None
    assert captured["access_log"] is False


def test_smoke_script_exits_nonzero_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("PROPILOT_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PROPILOT_LOG_LEVEL", "WARNING")

    from backend.runtime import main as smoke

    # Neutralise any .env on the developer's machine.
    real_get_settings = smoke.get_settings

    def settings_without_key() -> Any:
        return real_get_settings().model_copy(update={"openai_api_key": None})

    monkeypatch.setattr(smoke, "get_settings", settings_without_key)
    assert smoke.main() == 1


def test_smoke_script_prints_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PROPILOT_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PROPILOT_DEFAULT_MODEL", "test")
    monkeypatch.setenv("PROPILOT_LOG_LEVEL", "WARNING")

    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    from backend.runtime import main as smoke
    from backend.runtime.agent import AgentRegistry, AgentSpec

    def fake_registry(settings: Any) -> AgentRegistry:
        registry = AgentRegistry()
        registry.register(
            AgentSpec(
                name="atlas",
                description="d",
                model="test",
                agent=Agent(model=TestModel(custom_output_text="smoke ok"), name="atlas"),
            )
        )
        return registry

    monkeypatch.setattr(smoke, "build_registry", fake_registry)
    assert smoke.main() == 0
    assert "smoke ok" in capsys.readouterr().out
