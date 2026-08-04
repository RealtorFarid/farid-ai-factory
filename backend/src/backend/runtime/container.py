"""Composition root.

One place where the runtime object graph is assembled, so the wiring order is
explicit and testable. Everything above this — the API — receives finished
collaborators and never constructs its own.

Storage is chosen here and nowhere else: set ``PROPILOT_DATABASE_URL`` and the
same protocols are served from Postgres instead of memory. No caller changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.runtime.agent import AgentRegistry, build_registry
from backend.runtime.claims import ClaimStore, InMemoryClaimStore
from backend.runtime.config import Settings
from backend.runtime.events import EventBus
from backend.runtime.extraction import Extractor, build_extractor
from backend.runtime.logger import get_logger
from backend.runtime.orchestrator import AgentRunner
from backend.runtime.runs import InMemoryRunStore, RunStore
from backend.runtime.tools import ToolRegistry, build_default_tools
from backend.runtime.workspace import InMemoryWorkspaceStore, WorkspaceService, WorkspaceStore

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.db.engine import Database

__all__ = ["Runtime", "build_runtime"]

log = get_logger(__name__)


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
    claims: ClaimStore
    extractor: Extractor
    database: Database | None = None

    def shutdown(self) -> None:
        if self.database is not None:
            self.database.dispose()


def build_runtime(
    settings: Settings,
    *,
    store: WorkspaceStore | None = None,
    agents: AgentRegistry | None = None,
    runs: RunStore | None = None,
    claims: ClaimStore | None = None,
    database: Database | None = None,
) -> Runtime:
    """Assemble the runtime.

    Every collaborator is injectable so tests can supply a fixed workspace and
    an offline model without patching globals.
    """
    if store is None and runs is None and settings.persistence_enabled:
        database, store, runs, claims = _build_persistent(settings, database, claims)

    workspace = WorkspaceService(store or InMemoryWorkspaceStore())
    tools = build_default_tools(workspace)
    registry = agents if agents is not None else build_registry(settings, tools)
    run_store = runs if runs is not None else InMemoryRunStore()
    claim_store = claims if claims is not None else InMemoryClaimStore()
    bus = EventBus()

    runner = AgentRunner(
        agents=registry,
        runs=run_store,
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
        runs=run_store,
        bus=bus,
        runner=runner,
        claims=claim_store,
        extractor=build_extractor(settings, claim_store),
        database=database,
    )


def _build_persistent(
    settings: Settings, database: Database | None, claims: ClaimStore | None
) -> tuple[Database, WorkspaceStore, RunStore, ClaimStore]:
    """Wire the Postgres-backed stores. Imported lazily so the in-memory path
    never pays for the database dependencies."""
    from backend.db.engine import Database as Db
    from backend.db.repositories import (
        ClaimRepository,
        PostgresRunStore,
        PostgresWorkspaceStore,
    )
    from backend.db.seed import seed_workspace

    assert settings.database_url is not None
    db = database or Db(
        settings.database_url,
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
    )
    org = settings.default_org_id

    seeded = seed_workspace(db, org)
    log.info("runtime.persistence_enabled", org_id=org, seeded=seeded)

    return (
        db,
        PostgresWorkspaceStore(db, org),
        PostgresRunStore(db, org),
        claims or ClaimRepository(db, org),
    )
