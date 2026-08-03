"""FastAPI dependencies.

Shared objects live on ``app.state`` and are injected from there, so tests can
build an app with a stub registry and no global patching.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.runtime.agent import AgentRegistry
from backend.runtime.config import Settings

__all__ = ["RegistryDep", "SettingsDep", "get_registry", "get_settings_from_state"]


def get_settings_from_state(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_registry(request: Request) -> AgentRegistry:
    registry: AgentRegistry = request.app.state.registry
    return registry


SettingsDep = Annotated[Settings, Depends(get_settings_from_state)]
RegistryDep = Annotated[AgentRegistry, Depends(get_registry)]
