"""The event bus: fan-out, replay, backpressure and lifecycle."""

from __future__ import annotations

import asyncio

from backend.runtime.events import Event, EventBus, EventType


async def _drain(bus: EventBus, run_id: str, *, replay_from: int = 0) -> list[Event]:
    collected: list[Event] = []
    async with bus.subscribe(run_id, replay_from=replay_from) as events:
        async for event in events:
            collected.append(event)
    return collected


async def test_events_are_replayed_to_a_late_subscriber() -> None:
    bus = EventBus()
    bus.publish("run_1", EventType.RUN_STARTED, agent="atlas")
    bus.publish("run_1", EventType.RUN_TOKEN, delta="hi")
    bus.publish("run_1", EventType.RUN_COMPLETED, output="hi")
    bus.close("run_1")

    events = await _drain(bus, "run_1")

    assert [e.type for e in events] == [
        EventType.RUN_STARTED,
        EventType.RUN_TOKEN,
        EventType.RUN_COMPLETED,
    ]
    assert [e.sequence for e in events] == [1, 2, 3]


async def test_replay_from_skips_what_the_client_already_has() -> None:
    bus = EventBus()
    for index in range(5):
        bus.publish("run_1", EventType.RUN_TOKEN, delta=str(index))
    bus.close("run_1")

    events = await _drain(bus, "run_1", replay_from=3)
    assert [e.sequence for e in events] == [4, 5]


async def test_a_live_subscriber_receives_events_as_they_happen() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def consume() -> None:
        async with bus.subscribe("run_1") as events:
            async for event in events:
                received.append(event)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let the subscription register

    bus.publish("run_1", EventType.RUN_TOKEN, delta="a")
    bus.publish("run_1", EventType.RUN_COMPLETED, output="a")
    bus.close("run_1")
    await asyncio.wait_for(task, timeout=2)

    assert [e.type for e in received] == [EventType.RUN_TOKEN, EventType.RUN_COMPLETED]


async def test_two_subscribers_both_receive_everything() -> None:
    bus = EventBus()
    bus.publish("run_1", EventType.RUN_STARTED)
    bus.close("run_1")

    first, second = await asyncio.gather(_drain(bus, "run_1"), _drain(bus, "run_1"))
    assert len(first) == len(second) == 1


async def test_publish_never_blocks_on_a_stalled_subscriber() -> None:
    """A subscriber that cannot keep up is dropped, not allowed to stall the run."""
    bus = EventBus()

    async with bus.subscribe("run_1") as events:
        assert events is not None
        for index in range(1000):  # far beyond the subscriber queue size
            bus.publish("run_1", EventType.RUN_TOKEN, delta=str(index))

    # The run kept going and every event is still in the replay buffer.
    assert bus.subscriber_count("run_1") == 0
    assert len(bus.history("run_1")) > 0


async def test_reopen_allows_a_resumed_run_to_publish_again() -> None:
    bus = EventBus()
    bus.publish("run_1", EventType.APPROVAL_REQUIRED, tool_name="send_email")
    bus.close("run_1")

    bus.reopen("run_1")
    bus.publish("run_1", EventType.APPROVAL_RESOLVED, approved=True)
    bus.close("run_1")

    events = await _drain(bus, "run_1")
    assert [e.type for e in events] == [
        EventType.APPROVAL_REQUIRED,
        EventType.APPROVAL_RESOLVED,
    ]


async def test_forget_discards_a_run() -> None:
    bus = EventBus()
    bus.publish("run_1", EventType.RUN_STARTED)
    bus.forget("run_1")
    assert bus.history("run_1") == []


def test_payload_is_json_ready() -> None:
    bus = EventBus()
    event = bus.publish("run_1", EventType.TOOL_CALLED, tool_name="send_email", args={"a": 1})
    payload = event.to_payload()

    assert payload["type"] == "tool.called"
    assert payload["run_id"] == "run_1"
    assert payload["sequence"] == 1
    assert payload["data"]["tool_name"] == "send_email"
    assert isinstance(payload["created_at"], str)


def test_replay_buffer_is_bounded() -> None:
    bus = EventBus(replay_size=10)
    for index in range(50):
        bus.publish("run_1", EventType.RUN_TOKEN, delta=str(index))

    history = bus.history("run_1")
    assert len(history) == 10
    assert history[-1].sequence == 50
