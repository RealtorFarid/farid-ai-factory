"""Composition root.

One place where the runtime object graph is assembled, so the wiring order is
explicit and testable. Everything above this — the API — receives finished
collaborators and never constructs its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.runtime.agent import AgentRegistry, build_registry
from backend.runtime.config import Settings
from backend.runtime.events import EventBus
from backend.runtime.orchestrator import AgentRunner
from backend.runtime.runs import RunStore
from backend.runtime.tools import ToolRegistry, build_default_tools
from backend.runtime.workspace import InMemoryWorkspaceStore, WorkspaceService, WorkspaceStore

__all__ = ["Runtime", "build_runtime"]


@dataclass(frozen=True, slots=True)
class Runtime:
    """The assembled runtime, ready to serve."""

    settings: Settings
    workspace: WorkspaceService
    tools: ToolRegistry
    agents: AgentRegistry
    runs: RunStore
    bus: EventBus
    runner: AgentRunner


def build_runtime(
    settings: Settings,
    *,
    store: WorkspaceStore | None = None,
    agents: AgentRegistry | None = None,
) -> Runtime:
    """Assemble the runtime.

    ``store`` and ``agents`` are injectable so tests can supply a fixed
    workspace and an offline model without patching globals.
    """
    workspace = WorkspaceService(store or InMemoryWorkspaceStore())
    tools = build_default_tools(workspace)
    registry = agents if agents is not None else build_registry(settings, tools)
    runs = RunStore()
    bus = EventBus()

    runner = AgentRunner(
        agents=registry,
        runs=runs,
        bus=bus,
        tools=tools,
        timeout_seconds=settings.agent_timeout_seconds,
        max_prompt_chars=settings.max_prompt_chars,
    )

    return Runtime(
        settings=settings,
        workspace=workspace,
        tools=tools,
        agents=registry,
        runs=runs,
        bus=bus,
        runner=runner,
    )
