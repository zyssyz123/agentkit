"""EventBus unit tests."""

from __future__ import annotations

import pytest

from agentkit.events import Event, EventBus, EventType


@pytest.mark.asyncio
async def test_emit_calls_all_subscribers_in_order():
    bus = EventBus()
    received: list[str] = []

    async def s1(ev: Event) -> None:
        received.append(f"s1:{ev.type.value}")

    async def s2(ev: Event) -> None:
        received.append(f"s2:{ev.type.value}")

    bus.subscribe(s1)
    bus.subscribe(s2)
    await bus.emit(Event(type=EventType.RUN_STARTED))
    assert sorted(received) == ["s1:run.started", "s2:run.started"]


@pytest.mark.asyncio
async def test_subscriber_failure_does_not_break_others():
    bus = EventBus()
    survived: list[bool] = []

    async def boom(ev: Event) -> None:
        raise RuntimeError("boom")

    async def good(ev: Event) -> None:
        survived.append(True)

    bus.subscribe(boom)
    bus.subscribe(good)
    await bus.emit(Event(type=EventType.RUN_STARTED))
    assert survived == [True]


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = EventBus()
    seen: list[Event] = []

    async def s(ev: Event) -> None:
        seen.append(ev)

    unsub = bus.subscribe(s)
    await bus.emit(Event(type=EventType.RUN_STARTED))
    unsub()
    await bus.emit(Event(type=EventType.RUN_COMPLETED))
    assert [e.type for e in seen] == [EventType.RUN_STARTED]


def test_event_to_dict_roundtrip_payload():
    ev = Event(
        type=EventType.PLANNER_THOUGHT,
        element="planner",
        technique="react",
        payload={"thought": "hi"},
    )
    d = ev.to_dict()
    assert d["type"] == "planner.thought"
    assert d["payload"] == {"thought": "hi"}
    assert "ts" in d and "span_id" in d
