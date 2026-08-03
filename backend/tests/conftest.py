"""Shared test fixtures.

Two rules the suite enforces globally:

1. No test may reach the network — ``ALLOW_MODEL_REQUESTS`` is disabled, so a
   real model call raises instead of silently costing money.
2. No test may read the developer's ``.env`` — every ``Settings`` is built with
   ``_env_file=None`` so results do not depend on the machine.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai import Agent, models
from pydantic_ai.models.test import TestModel

from backend.api.app import create_app
from backend.runtime.agent import AgentRegistry, AgentSpec
from backend.runtime.config import Settings

STUB_OUTPUT = "Atlas here. Plan: 1) gather facts 2) draft 3) review."

models.ALLOW_MODEL_REQUESTS = False


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
def registry() -> AgentRegistry:
    """A registry whose only agent is backed by an offline stub model."""
    reg = AgentRegistry()
    reg.register(
        AgentSpec(
            name="atlas",
            description="Executive agent: turns goals into concrete, ordered plans.",
            model="test",
            agent=Agent(
                model=TestModel(custom_output_text=STUB_OUTPUT),
                system_prompt="test system prompt",
                name="atlas",
            ),
        )
    )
    return reg


@pytest.fixture
def app(settings: Settings, registry: AgentRegistry) -> FastAPI:
    return create_app(settings=settings, registry=registry)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that exercises startup and shutdown, like the real server."""
    with TestClient(app) as test_client:
        yield test_client
