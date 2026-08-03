"""Shared test fixtures.

Two rules the suite enforces globally:

1. No test may reach the network — ``ALLOW_MODEL_REQUESTS`` is disabled, so a
   real model call raises instead of silently costing money.
2. No test may read the developer's ``.env`` — every ``Settings`` is built with
   ``_env_file=None`` so results do not depend on the machine.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent, DeferredToolRequests, models
from pydantic_ai.models.test import TestModel

from backend.api.app import create_app
from backend.runtime.agent import AgentRegistry, AgentSpec
from backend.runtime.config import Settings
from backend.runtime.container import Runtime, build_runtime
from backend.runtime.tools import ToolRegistry, build_default_tools
from backend.runtime.workspace import InMemoryWorkspaceStore, WorkspaceService

STUB_OUTPUT = "Atlas here. Plan: 1) gather facts 2) draft 3) review."

models.ALLOW_MODEL_REQUESTS = False

# A fixed instant so seeded workspace data is identical on every run.
FROZEN_NOW = datetime(2026, 3, 17, 9, 30, tzinfo=UTC)


@pytest.fixture
def clock() -> Callable[[], datetime]:
    return lambda: FROZEN_NOW


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings, isolated from the developer's environment."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="development",
        debug=False,
        log_level="WARNING",
        log_format="console",
        cors_origins=["http://testserver"],
        openai_api_key="sk-test-not-a-real-key",  # type: ignore[arg-type]
        default_model="test",
        agent_timeout_seconds=5.0,
        max_prompt_chars=200,
    )


@pytest.fixture
def workspace(clock: Callable[[], datetime]) -> WorkspaceService:
    return WorkspaceService(InMemoryWorkspaceStore(clock=clock))


@pytest.fixture
def tools(workspace: WorkspaceService) -> ToolRegistry:
    return build_default_tools(workspace)


def make_registry(
    *, tools: ToolRegistry | None = None, output_text: str = STUB_OUTPUT
) -> AgentRegistry:
    """A registry whose only agent is backed by an offline stub model."""
    registry = AgentRegistry()
    registry.register(
        AgentSpec(
            name="atlas",
            description="Executive agent: turns goals into concrete, ordered plans.",
            model="test",
            agent=Agent(
                model=TestModel(custom_output_text=output_text, call_tools=[]),
                system_prompt="test system prompt",
                name="atlas",
                output_type=[str, DeferredToolRequests],
                tools=tools.as_pydantic_tools() if tools else [],
            ),
        )
    )
    return registry


@pytest.fixture
def registry(tools: ToolRegistry) -> AgentRegistry:
    """Default agent: answers with text and calls no tools."""
    return make_registry(tools=tools)


@pytest.fixture
def runtime(settings: Settings, clock: Callable[[], datetime], registry: AgentRegistry) -> Runtime:
    return build_runtime(settings, store=InMemoryWorkspaceStore(clock=clock), agents=registry)


def make_runtime(
    settings: Settings,
    *,
    agents: AgentRegistry | None = None,
    clock: Callable[[], datetime] = lambda: FROZEN_NOW,
) -> Runtime:
    """Build a runtime for a test that needs a non-default agent."""
    return build_runtime(
        settings,
        store=InMemoryWorkspaceStore(clock=clock),
        agents=agents if agents is not None else make_registry(),
    )


@pytest.fixture
def app(settings: Settings, runtime: Runtime) -> FastAPI:
    return create_app(settings=settings, runtime=runtime)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that exercises startup and shutdown, like the real server."""
    with TestClient(app) as test_client:
        yield test_client
