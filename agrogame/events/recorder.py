from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from .base import BaseEvent
from .bus import EventBus


@dataclass
class RecordedEvent:
    day_index: Optional[int]
    event_type: str
    data: Dict[str, Any]


class EventRecorder:
    """Subscribe to BaseEvent and keep an in-memory log for visualization."""

    def __init__(self, bus: EventBus) -> None:
        self._events: List[RecordedEvent] = []
        self._current_day: Optional[int] = None
        bus.subscribe(BaseEvent, self._on_event)

    def set_day(self, day_index: int) -> None:
        self._current_day = day_index

    def _on_event(self, event: BaseEvent) -> None:
        data = event.to_dict()
        etype = data.pop("event_type", type(event).__name__)
        self._events.append(RecordedEvent(self._current_day, etype, data))

    @property
    def events(self) -> Sequence[RecordedEvent]:
        return tuple(self._events)
