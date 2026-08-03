"""Agent execution: timeouts, prompt limits and usage accounting."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from backend.runtime.agent import (
    AgentNotFoundError,
    AgentRegistry,
    AgentSpec,
    build_registry,
    resolve_model,
)
from backend.runtime.config import Settings
from backend.runtime.runner import (
    AgentTimeoutError,
    DoneEvent,
    PromptTooLongError,
    TokenEvent,
    run_agent,
    stream_agent,
    validate_prompt,
)


def _spec(agent: Any, name: str = "atlas") -> AgentSpec:
    return AgentSpec(name=name, description="d", model="test", agent=agent)


def _stub_agent(text: str = "hello") -> Agent[None, str]:
    return Agent(model=TestModel(custom_output_text=text), system_prompt="sp", name="atlas")


# ---- Prompt validation ---------------------------------------------------


def test_validate_prompt_allows_prompt_at_the_limit() -> None:
    validate_prompt("x" * 10, 10)


def test_validate_prompt_rejects_one_over_the_limit() -> None:
    with pytest.raises(PromptTooLongError) as excinfo:
        validate_prompt("x" * 11, 10)
    assert excinfo.value.length == 11
    assert excinfo.value.limit == 10


# ---- Runs ----------------------------------------------------------------


async def test_run_agent_returns_output_and_usage() -> None:
    outcome = await run_agent(_spec(_stub_agent("done")), "go", timeout_seconds=5)
    assert outcome.output == "done"
    assert outcome.usage.output_tokens > 0
    assert outcome.usage.requests == 1
    assert outcome.duration_ms >= 0


async def test_run_agent_times_out() -> None:
    class SlowAgent:
        async def run(self, prompt: str) -> object:
            await asyncio.sleep(10)
            raise AssertionError("should not be reached")

    with pytest.raises(AgentTimeoutError) as excinfo:
        await run_agent(_spec(SlowAgent()), "go", timeout_seconds=0.05)
    assert excinfo.value.timeout_seconds == 0.05


async def test_stream_agent_yields_tokens_then_done() -> None:
    events = [e async for e in stream_agent(_spec(_stub_agent("abc")), "go", timeout_seconds=5)]
    assert isinstance(events[-1], DoneEvent)
    assert all(isinstance(e, TokenEvent) for e in events[:-1])
    assert "".join(e.delta for e in events if isinstance(e, TokenEvent)) == "abc"
    assert events[-1].output == "abc"


# ---- Registry ------------------------------------------------------------


def test_registry_get_and_default() -> None:
    registry = AgentRegistry()
    registry.register(_spec(_stub_agent(), name="alpha"))
    registry.register(_spec(_stub_agent(), name="beta"))
    assert registry.default.name == "alpha"
    assert registry.get("beta").name == "beta"
    assert registry.names() == ["alpha", "beta"]
    assert "alpha" in registry
    assert len(registry) == 2


def test_registry_rejects_duplicate_names() -> None:
    registry = AgentRegistry()
    registry.register(_spec(_stub_agent(), name="alpha"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_spec(_stub_agent(), name="alpha"))


def test_registry_raises_for_unknown_agent() -> None:
    with pytest.raises(AgentNotFoundError) as excinfo:
        AgentRegistry().get("ghost")
    assert excinfo.value.name == "ghost"


def test_empty_registry_has_no_default() -> None:
    with pytest.raises(AgentNotFoundError):
        _ = AgentRegistry().default


def test_build_registry_uses_configured_model() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, default_model="openai:gpt-4o", log_level="WARNING"
    )
    registry = build_registry(settings)
    assert registry.default.name == "atlas"
    assert registry.default.model == "openai:gpt-4o"


# ---- Model resolution ----------------------------------------------------


def _model_settings(**overrides: object) -> Settings:
    """Settings with credentials forced off unless a test opts in."""
    settings = Settings(_env_file=None, log_level="WARNING", **overrides)  # type: ignore[arg-type, call-arg]
    if "openai_api_key" not in overrides:
        settings = settings.model_copy(update={"openai_api_key": None})
    return settings


def test_resolve_model_passes_through_non_openai_specs() -> None:
    assert resolve_model(_model_settings(default_model="test")) == "test"


def test_resolve_model_builds_openai_model_from_configured_key() -> None:
    model = resolve_model(
        _model_settings(default_model="openai:gpt-4o", openai_api_key="sk-configured")
    )
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "gpt-4o"


def test_resolve_model_still_builds_without_credentials() -> None:
    """Missing credentials must degrade readiness, not prevent the process booting."""
    model = resolve_model(_model_settings(default_model="openai:gpt-4o"))
    assert isinstance(model, OpenAIChatModel)
