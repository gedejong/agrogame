from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent, EventBus
from agrogame.events.recorder import EventRecorder


@dataclass(frozen=True)
class DummyEvent(BaseEvent):
    value: int


def test_baseevent_subscription_and_recording() -> None:
    bus = EventBus()
    rec = EventRecorder(bus)
    # Also subscribe a BaseEvent handler to ensure catch-all works
    seen = {"count": 0}

    def on_any(e: BaseEvent) -> None:
        seen["count"] += 1

    bus.subscribe(BaseEvent, on_any)

    rec.set_day(3)
    bus.emit(DummyEvent(value=42))

    assert seen["count"] == 1
    assert len(rec.events) == 1
    ev = rec.events[0]
    assert ev.day_index == 3
    assert ev.event_type == "DummyEvent"
    assert ev.data["value"] == 42


def test_clear_empties_recorded_events() -> None:
    bus = EventBus()
    rec = EventRecorder(bus)
    rec.set_day(1)
    bus.emit(DummyEvent(value=1))
    bus.emit(DummyEvent(value=2))
    assert len(rec.events) == 2
    rec.clear()
    assert len(rec.events) == 0
    bus.emit(DummyEvent(value=3))
    assert len(rec.events) == 1
