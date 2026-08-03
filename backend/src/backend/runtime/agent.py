"""Agent definitions and the runtime agent registry.

Agents are built from a :class:`Settings` instance rather than reading the
environment themselves, which keeps them trivially testable: a test can build
a registry against a ``TestModel`` without touching a network.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from backend.runtime.config import Settings
from backend.runtime.stub import STUB_MODEL_NAME, build_stub_model

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.runtime.tools import ToolRegistry

__all__ = [
    "AgentNotFoundError",
    "AgentRegistry",
    "AgentSpec",
    "build_registry",
    "resolve_model",
]


class AgentNotFoundError(KeyError):
    """Raised when a caller asks for an agent that is not registered."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """A registered agent plus the metadata the API exposes about it."""

    name: str
    description: str
    model: str
    # Output is `str | DeferredToolRequests`: a gated tool makes the agent
    # return a request for approval instead of an answer.
    agent: Agent[None, Any]


class AgentRegistry:
    """An ordered, name-addressable collection of agents."""

    def __init__(self, default: str | None = None) -> None:
        self._agents: dict[str, AgentSpec] = {}
        self._default = default

    def register(self, spec: AgentSpec) -> None:
        if spec.name in self._agents:
            raise ValueError(f"agent {spec.name!r} is already registered")
        self._agents[spec.name] = spec
        if self._default is None:
            self._default = spec.name

    def get(self, name: str) -> AgentSpec:
        try:
            return self._agents[name]
        except KeyError:
            raise AgentNotFoundError(name) from None

    @property
    def default(self) -> AgentSpec:
        if self._default is None:
            raise AgentNotFoundError("<default>")
        return self.get(self._default)

    def names(self) -> list[str]:
        return list(self._agents)

    def __iter__(self) -> Iterator[AgentSpec]:
        return iter(self._agents.values())

    def __contains__(self, name: object) -> bool:
        return name in self._agents

    def __len__(self) -> int:
        return len(self._agents)


ATLAS_SYSTEM_PROMPT = """\
You are Atlas, the executive agent of Propilot AI — an AI operating system for
real-estate professionals.

How you work:
- Understand the goal before acting; restate it in one line if it is ambiguous.
- Break work into concrete, ordered, verifiable tasks.
- Think step by step, but present only the conclusion and the plan.
- Never guess. If a fact is missing, say what is missing and ask for it.
- Prefer evidence over assertion; cite the source of any figure you use.
- Keep answers concise and actionable.

Using tools:
- Read the workspace before answering questions about tasks, leads, email or
  the calendar. Do not estimate what you can look up.
- Sending email, booking time and completing tasks need the user's approval.
  Propose them plainly and let the approval gate do its job — never imply an
  action has happened before it is approved.
- After an action is denied, acknowledge it and offer an alternative.
"""


def resolve_model(settings: Settings) -> Model | str:
    """Turn ``Settings.default_model`` into something an ``Agent`` can use.

    For OpenAI we build the provider explicitly so the credential comes from
    :class:`Settings` rather than ambient environment state. When no key is
    configured we still construct the model with a placeholder: the process
    must be able to boot and report itself degraded via ``/health/ready``
    rather than crash-loop before it can answer any probe. A real request then
    fails with an authentication error, which is the honest outcome.
    """
    spec = settings.default_model
    if spec == STUB_MODEL_NAME:
        return build_stub_model()
    if not spec.startswith("openai:"):
        return spec

    key = (
        settings.openai_api_key.get_secret_value()
        if settings.openai_api_key is not None
        else "not-configured"
    )
    return OpenAIChatModel(spec.removeprefix("openai:"), provider=OpenAIProvider(api_key=key))


def build_registry(settings: Settings, tools: ToolRegistry | None = None) -> AgentRegistry:
    """Construct the registry of agents available to this process.

    ``output_type`` includes :class:`DeferredToolRequests` so that a tool marked
    ``requires_approval`` suspends the run and surfaces as a pending approval
    instead of executing. That union is what makes the approval gate structural
    rather than advisory.
    """
    registry = AgentRegistry()
    registry.register(
        AgentSpec(
            name="atlas",
            description="Executive agent: turns goals into concrete, ordered plans.",
            model=settings.default_model,
            agent=Agent(
                model=resolve_model(settings),
                system_prompt=ATLAS_SYSTEM_PROMPT,
                name="atlas",
                output_type=[str, DeferredToolRequests],
                tools=tools.as_pydantic_tools() if tools else [],
            ),
        )
    )
    return registry
