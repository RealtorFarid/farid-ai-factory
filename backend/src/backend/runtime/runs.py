"""Run lifecycle state.

A run is one agent conversation. It may pause partway through, waiting for the
user to approve a tool call, and resume later — so unlike a plain request it
needs somewhere to live between HTTP calls.

Storage is an in-memory bounded store. Phase 2 moves it to PostgreSQL; the
:class:`RunStore` interface is what the API and orchestrator depend on, so that
swap does not reach above this module.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pydantic_ai import DeferredToolRequests
    from pydantic_ai.messages import ModelMessage

from backend.runtime.runner import UsageSnapshot

__all__ = [
    "ApprovalDecision",
    "PendingApproval",
    "Run",
    "RunNotFoundError",
    "RunStatus",
    "RunStore",
    "ToolCallRecord",
]

MAX_RUNS = 500


class RunStatus(StrEnum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class RunNotFoundError(KeyError):
    def __init__(self, run_id: str) -> None:
        super().__init__(run_id)
        self.run_id = run_id


@dataclass(frozen=True, slots=True)
class PendingApproval:
    """A tool call the agent wants to make, blocked on the user's decision."""

    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    description: str = ""


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """The user's answer to a :class:`PendingApproval`."""

    tool_call_id: str
    approved: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """An executed tool call, kept as the run's audit trail."""

    tool_name: str
    tool_call_id: str
    args: dict[str, Any]
    approved: bool | None = None


@dataclass(slots=True)
class Run:
    id: str
    agent: str
    model: str
    prompt: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    session_id: str | None = None
    output: str | None = None
    error: str | None = None
    error_code: str | None = None
    usage: UsageSnapshot | None = None
    duration_ms: int = 0
    pending_approvals: list[PendingApproval] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)

    # Internal continuation state. Not serialised to API clients: these are
    # PydanticAI objects, and exposing them would freeze an internal format
    # into the public contract.
    messages: list[ModelMessage] = field(default_factory=list)
    deferred: DeferredToolRequests | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (RunStatus.COMPLETED, RunStatus.FAILED)

    def touch(self) -> None:
        self.updated_at = datetime.now(UTC)


class RunStore:
    """A bounded, insertion-ordered store of runs.

    Oldest runs are evicted once ``max_runs`` is exceeded, so a long-lived
    process cannot grow without limit. Approval-blocked runs are evicted too:
    an abandoned approval is not worth leaking memory over, and the API returns
    a clean 404 afterwards.
    """

    def __init__(self, max_runs: int = MAX_RUNS) -> None:
        self._runs: OrderedDict[str, Run] = OrderedDict()
        self._max_runs = max_runs

    def create(self, *, agent: str, model: str, prompt: str, session_id: str | None = None) -> Run:
        now = datetime.now(UTC)
        run = Run(
            id=f"run_{uuid4().hex[:16]}",
            agent=agent,
            model=model,
            prompt=prompt,
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
            session_id=session_id,
        )
        self._runs[run.id] = run
        self._evict()
        return run

    def get(self, run_id: str) -> Run:
        run = self._runs.get(run_id)
        if run is None:
            raise RunNotFoundError(run_id)
        self._runs.move_to_end(run_id)
        return run

    def list(self, *, limit: int = 50, session_id: str | None = None) -> list[Run]:
        runs = list(self._runs.values())
        if session_id is not None:
            runs = [run for run in runs if run.session_id == session_id]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)[:limit]

    def _evict(self) -> None:
        while len(self._runs) > self._max_runs:
            self._runs.popitem(last=False)

    def __len__(self) -> int:
        return len(self._runs)

    def __contains__(self, run_id: object) -> bool:
        return run_id in self._runs
