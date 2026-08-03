"""In-process event bus for agent runs.

Every interesting thing that happens during a run is published here: tokens,
tool calls, approval requests, completion. Transports subscribe; they do not
reach into the runner. That indirection is what lets a second client attach to
a run already in flight, and what will let Phase 2 fan the same events out to
tracing and an audit log without touching the runner again.

Each run keeps a bounded replay buffer, so a subscriber that attaches late (a
browser reconnecting, a second tab) still sees what it missed.

Scope: single process. Phase 4 swaps the implementation for Redis pub/sub when
there is more than one worker; the interface is designed not to change.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from backend.runtime.logger import get_logger

__all__ = ["Event", "EventBus", "EventType"]

log = get_logger(__name__)

REPLAY_BUFFER_SIZE = 512
SUBSCRIBER_QUEUE_SIZE = 256


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    RUN_TOKEN = "run.token"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    TOOL_CALLED = "tool.called"
    APPROVAL_REQUIRED = "approval.required"
    APPROVAL_RESOLVED = "approval.resolved"
    RUN_RESUMED = "run.resumed"


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    run_id: str
    sequence: int
    created_at: datetime
    data: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "created_at": self.created_at.isoformat(),
            "data": self.data,
        }


@dataclass(slots=True)
class _Channel:
    buffer: deque[Event]
    subscribers: set[asyncio.Queue[Event | None]]
    sequence: int = 0
    closed: bool = False


class EventBus:
    """Fan-out of run events to any number of subscribers."""

    def __init__(self, replay_size: int = REPLAY_BUFFER_SIZE) -> None:
        self._replay_size = replay_size
        self._channels: dict[str, _Channel] = {}

    # ---- Publishing ------------------------------------------------------

    def _channel(self, run_id: str) -> _Channel:
        channel = self._channels.get(run_id)
        if channel is None:
            channel = _Channel(buffer=deque(maxlen=self._replay_size), subscribers=set())
            self._channels[run_id] = channel
        return channel

    def publish(self, run_id: str, event_type: EventType, **data: Any) -> Event:
        """Publish an event. Never blocks and never raises on a slow subscriber."""
        channel = self._channel(run_id)
        channel.sequence += 1
        event = Event(
            type=event_type,
            run_id=run_id,
            sequence=channel.sequence,
            created_at=datetime.now(UTC),
            data=data,
        )
        channel.buffer.append(event)

        for queue in list(channel.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A subscriber that cannot keep up is dropped rather than
                # allowed to stall the run that is producing the events.
                log.warning("events.subscriber_lagging", run_id=run_id, dropped=event_type.value)
                channel.subscribers.discard(queue)
        return event

    def close(self, run_id: str) -> None:
        """Signal end-of-stream to every subscriber of a run."""
        channel = self._channels.get(run_id)
        if channel is None:
            return
        channel.closed = True
        for queue in list(channel.subscribers):
            with _suppress_full(queue):
                queue.put_nowait(None)

    def reopen(self, run_id: str) -> None:
        """Mark a closed run as live again (a resumed run publishes more events)."""
        channel = self._channels.get(run_id)
        if channel is not None:
            channel.closed = False

    def forget(self, run_id: str) -> None:
        self._channels.pop(run_id, None)

    # ---- Subscribing -----------------------------------------------------

    @asynccontextmanager
    async def subscribe(
        self, run_id: str, *, replay_from: int = 0
    ) -> AsyncIterator[AsyncIterator[Event]]:
        """Subscribe to a run's events, replaying anything already emitted.

        ``replay_from`` is the last sequence number the client already has, so a
        reconnecting browser can resume without duplicates.
        """
        channel = self._channel(run_id)
        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        backlog = [event for event in channel.buffer if event.sequence > replay_from]
        was_closed = channel.closed
        channel.subscribers.add(queue)

        async def iterator() -> AsyncIterator[Event]:
            for event in backlog:
                yield event
            # A run that already finished has nothing further to send; replaying
            # the backlog is the whole subscription.
            if was_closed:
                return
            while True:
                item = await queue.get()
                if item is None:  # terminal sentinel from close()
                    return
                yield item

        try:
            yield iterator()
        finally:
            channel.subscribers.discard(queue)

    # ---- Introspection ---------------------------------------------------

    def history(self, run_id: str) -> list[Event]:
        channel = self._channels.get(run_id)
        return list(channel.buffer) if channel else []

    def subscriber_count(self, run_id: str) -> int:
        channel = self._channels.get(run_id)
        return len(channel.subscribers) if channel else 0


class _suppress_full:
    """Context manager that ignores a full queue, for terminal sentinels."""

    def __init__(self, queue: asyncio.Queue[Event | None]) -> None:
        self._queue = queue

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return exc_type is asyncio.QueueFull
