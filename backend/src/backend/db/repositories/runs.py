"""Postgres implementation of the run store.

The point of this file is one behaviour: a run paused on an approval survives a
restart. That requires persisting PydanticAI's message history and its pending
deferred-tool requests, which are serialised with that library's own type
adapters and stored as opaque JSON — an internal format we keep, not a schema
we own. They are never queried.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelMessagesTypeAdapter
from sqlalchemy import func, select

from backend.db.engine import Database
from backend.db.models import RunRow, RunToolCallRow
from backend.runtime.logger import get_logger
from backend.runtime.runner import UsageSnapshot
from backend.runtime.runs import (
    PendingApproval,
    Run,
    RunNotFoundError,
    RunStatus,
    ToolCallRecord,
    ToolCallStatus,
)

__all__ = ["PostgresRunStore"]

log = get_logger(__name__)

_DEFERRED = TypeAdapter(DeferredToolRequests)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class PostgresRunStore:
    """Durable runs. Same surface as the in-memory store, plus ``save``."""

    def __init__(self, db: Database, org_id: str) -> None:
        self._db = db
        self._org_id = org_id

    # ---- Lifecycle -------------------------------------------------------

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
        with self._db.session() as s:
            s.add(
                RunRow(
                    id=run.id,
                    org_id=self._org_id,
                    agent=agent,
                    model=model,
                    prompt=prompt,
                    session_id=session_id,
                    status=run.status.value,
                    created_at=now,
                    updated_at=now,
                )
            )
        return run

    def get(self, run_id: str) -> Run:
        with self._db.session() as s:
            row = s.get(RunRow, run_id)
            if row is None or row.org_id != self._org_id:
                raise RunNotFoundError(run_id)
            calls = list(
                s.scalars(select(RunToolCallRow).where(RunToolCallRow.run_id == run_id)).all()
            )
            return self._to_run(row, calls)

    def list(self, *, limit: int = 50, session_id: str | None = None) -> list[Run]:
        with self._db.session() as s:
            query = (
                select(RunRow)
                .where(RunRow.org_id == self._org_id)
                .order_by(RunRow.created_at.desc())
                .limit(limit)
            )
            if session_id is not None:
                query = query.where(RunRow.session_id == session_id)
            rows = s.scalars(query).all()
            if not rows:
                return []

            # One query for every run's calls, rather than one per run.
            call_rows = s.scalars(
                select(RunToolCallRow).where(RunToolCallRow.run_id.in_([r.id for r in rows]))
            ).all()
            by_run: dict[str, list[RunToolCallRow]] = {}
            for call in call_rows:
                by_run.setdefault(call.run_id, []).append(call)

            return [self._to_run(row, by_run.get(row.id, [])) for row in rows]

    def save(self, run: Run) -> None:
        """Persist the current state of a run, including continuation state."""
        with self._db.session() as s:
            row = s.get(RunRow, run.id)
            if row is None:
                raise RunNotFoundError(run.id)

            row.status = run.status.value
            row.output = run.output
            row.error = run.error
            row.error_code = run.error_code
            row.duration_ms = run.duration_ms
            row.updated_at = run.updated_at
            row.usage = (
                {
                    "input_tokens": run.usage.input_tokens,
                    "output_tokens": run.usage.output_tokens,
                    "total_tokens": run.usage.total_tokens,
                    "requests": run.usage.requests,
                }
                if run.usage
                else None
            )

            # Continuation state — the reason an approval survives a restart.
            row.messages_json = (
                ModelMessagesTypeAdapter.dump_json(run.messages).decode() if run.messages else None
            )
            row.deferred_json = (
                _DEFERRED.dump_json(run.deferred).decode() if run.deferred is not None else None
            )
            row.pending_approvals = [
                {
                    "tool_call_id": p.tool_call_id,
                    "tool_name": p.tool_name,
                    "args": p.args,
                    "description": p.description,
                }
                for p in run.pending_approvals
            ] or None

            # Tool calls are upserted by (run_id, tool_call_id): a call's status
            # changes over its life, and duplicating rows would corrupt the audit.
            existing = {
                c.tool_call_id: c
                for c in s.scalars(
                    select(RunToolCallRow).where(RunToolCallRow.run_id == run.id)
                ).all()
            }
            for call in run.tool_calls:
                target = existing.get(call.tool_call_id)
                if target is None:
                    s.add(
                        RunToolCallRow(
                            id=f"tc_{uuid4().hex[:16]}",
                            run_id=run.id,
                            tool_call_id=call.tool_call_id,
                            tool_name=call.tool_name,
                            args=call.args,
                            status=call.status.value,
                            approved=call.approved,
                            error=call.error,
                            requires_approval=call.requires_approval,
                        )
                    )
                else:
                    target.status = call.status.value
                    target.approved = call.approved
                    target.error = call.error
                    target.args = call.args
                    target.requires_approval = call.requires_approval

    # ---- Mapping ---------------------------------------------------------

    def _to_run(self, row: RunRow, calls: Sequence[RunToolCallRow]) -> Run:
        run = Run(
            id=row.id,
            agent=row.agent,
            model=row.model,
            prompt=row.prompt,
            status=RunStatus(row.status),
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
            session_id=row.session_id,
            output=row.output,
            error=row.error,
            error_code=row.error_code,
            duration_ms=row.duration_ms,
        )
        if row.usage:
            run.usage = UsageSnapshot(
                input_tokens=int(row.usage.get("input_tokens", 0)),
                output_tokens=int(row.usage.get("output_tokens", 0)),
                total_tokens=int(row.usage.get("total_tokens", 0)),
                requests=int(row.usage.get("requests", 0)),
            )

        run.tool_calls = [
            ToolCallRecord(
                tool_name=c.tool_name,
                tool_call_id=c.tool_call_id,
                args=dict(c.args or {}),
                status=ToolCallStatus(c.status),
                approved=c.approved,
                error=c.error,
                requires_approval=c.requires_approval,
            )
            for c in calls
        ]
        run.pending_approvals = [
            PendingApproval(
                tool_call_id=str(p["tool_call_id"]),
                tool_name=str(p["tool_name"]),
                args=dict(p.get("args") or {}),
                description=str(p.get("description") or ""),
            )
            for p in (row.pending_approvals or [])
        ]

        # Rehydrating these is what lets a paused run resume in a new process.
        if row.messages_json:
            run.messages = list(ModelMessagesTypeAdapter.validate_json(row.messages_json))
        if row.deferred_json:
            run.deferred = _DEFERRED.validate_json(row.deferred_json)
        return run

    # ---- Introspection ---------------------------------------------------

    def __contains__(self, run_id: object) -> bool:
        with self._db.session() as s:
            count = s.scalar(select(func.count()).select_from(RunRow).where(RunRow.id == run_id))
            return bool(count)

    def __len__(self) -> int:
        with self._db.session() as s:
            return int(
                s.scalar(
                    select(func.count()).select_from(RunRow).where(RunRow.org_id == self._org_id)
                )
                or 0
            )

    def stats(self) -> dict[str, Any]:
        """Run counts by status — for the readiness probe and ops."""
        with self._db.session() as s:
            rows = s.execute(
                select(RunRow.status, func.count())
                .where(RunRow.org_id == self._org_id)
                .group_by(RunRow.status)
            ).all()
        return {status: count for status, count in rows}
