"""The workspace domain: the real-estate data an agent reasons about.

One service backs two consumers — the agent tool registry and the REST API —
so the numbers an agent quotes and the numbers a user sees can never diverge.

Storage is an in-memory seeded store today. It sits behind the
:class:`WorkspaceStore` protocol so the Phase 2 PostgreSQL implementation is a
drop-in replacement with no changes above this layer.
"""

from __future__ import annotations

from backend.runtime.workspace.models import (
    CalendarEvent,
    CalendarSummary,
    Dashboard,
    EmailSummary,
    EmailThread,
    EventKind,
    Lead,
    LeadStage,
    LeadSummary,
    Suggestion,
    Task,
    TaskPriority,
    TaskStatus,
)
from backend.runtime.workspace.service import WorkspaceService
from backend.runtime.workspace.store import InMemoryWorkspaceStore, WorkspaceStore

__all__ = [
    "CalendarEvent",
    "CalendarSummary",
    "Dashboard",
    "EmailSummary",
    "EmailThread",
    "EventKind",
    "InMemoryWorkspaceStore",
    "Lead",
    "LeadStage",
    "LeadSummary",
    "Suggestion",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "WorkspaceService",
    "WorkspaceStore",
]
