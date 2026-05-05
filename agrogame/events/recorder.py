"""In-memory event recorder used by tests and visualization tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Sequence

from .base import BaseEvent
from .bus import EventBus


@dataclass
class RecordedEvent:
    """One captured event with the day index it was emitted on."""

    day_index: int | None
    event_type: str
    module_name: str
    data: dict[str, Any]


class EventRecorder:
    """Subscribe to BaseEvent and keep an in-memory log for visualization."""

    def __init__(self, bus: EventBus) -> None:
        """Subscribe to BaseEvent on `bus` and start with an empty log."""
        self._events: list[RecordedEvent] = []
        self._current_day: int | None = None
        bus.subscribe(BaseEvent, self._on_event)

    def set_day(self, day_index: int) -> None:
        """Tag subsequent recorded events with `day_index` until changed."""
        self._current_day = day_index

    def _on_event(self, event: BaseEvent) -> None:
        data = event.to_dict()
        etype = data.pop("event_type", type(event).__name__)
        module_name = type(event).__module__
        self._events.append(RecordedEvent(self._current_day, etype, module_name, data))

    def clear(self) -> None:
        """Reset recorded events (call between simulation steps)."""
        self._events.clear()

    @property
    def events(self) -> Sequence[RecordedEvent]:
        """Immutable snapshot of all events recorded so far."""
        return tuple(self._events)
