"""FastAPI dependencies.

Shared objects live on ``app.state`` and are injected from there, so tests can
build an app with stub collaborators and no global patching.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.runtime.agent import AgentRegistry
from backend.runtime.claims import ClaimStore
from backend.runtime.config import Settings
from backend.runtime.container import Runtime
from backend.runtime.events import EventBus
from backend.runtime.extraction import Extractor
from backend.runtime.orchestrator import AgentRunner
from backend.runtime.runs import RunStore
from backend.runtime.tools import ToolRegistry
from backend.runtime.workspace import WorkspaceService

__all__ = [
    "BusDep",
    "ClaimsDep",
    "ExtractorDep",
    "RegistryDep",
    "RunStoreDep",
    "RunnerDep",
    "RuntimeDep",
    "SettingsDep",
    "ToolsDep",
    "WorkspaceDep",
]


def get_settings_from_state(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_registry(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.registry
    return registry


def get_tools(request: Request) -> ToolRegistry:
    tools: ToolRegistry = request.app.state.tools
    return tools


def get_workspace(request: Request) -> WorkspaceService:
    workspace: WorkspaceService = request.app.state.workspace
    return workspace


def get_runs(request: Request) -> RunStore:
    runs: RunStore = request.app.state.runs
    return runs


def get_bus(request: Request) -> EventBus:
    bus: EventBus = request.app.state.bus
    return bus


def get_runner(request: Request) -> AgentRunner:
    runner: AgentRunner = request.app.state.runner
    return runner


def get_claims(request: Request) -> ClaimStore:
    claims: ClaimStore = request.app.state.claims
    return claims


def get_extractor(request: Request) -> Extractor:
    extractor: Extractor = request.app.state.extractor
    return extractor


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime = request.app.state.runtime
    return runtime


ClaimsDep = Annotated[ClaimStore, Depends(get_claims)]
ExtractorDep = Annotated[Extractor, Depends(get_extractor)]
RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]
RegistryDep = Annotated[AgentRegistry, Depends(get_registry)]
ToolsDep = Annotated[ToolRegistry, Depends(get_tools)]
WorkspaceDep = Annotated[WorkspaceService, Depends(get_workspace)]
RunStoreDep = Annotated[RunStore, Depends(get_runs)]
BusDep = Annotated[EventBus, Depends(get_bus)]
RunnerDep = Annotated[AgentRunner, Depends(get_runner)]
