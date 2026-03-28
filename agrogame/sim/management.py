"""Management plan for scheduling irrigation and fertilizer events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ManagementEvent:
    """A single scheduled management action.

    Args:
        day: Day number (0-indexed from season start) to execute.
        action: One of "irrigate" or "fertilize".
        params: Action-specific parameters.
            For "irrigate": {"amount_mm": float}
            For "fertilize": {"type": str, "amount_kg_ha": float}
    """

    day: int
    action: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"day": self.day, "action": self.action, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManagementEvent:
        return cls(
            day=int(data["day"]),
            action=str(data["action"]),
            params=dict(data["params"]),
        )


@dataclass
class ManagementPlan:
    """A collection of scheduled management events for a season."""

    events: list[ManagementEvent] = field(default_factory=list)

    def events_for_day(self, day: int) -> list[ManagementEvent]:
        """Return all events scheduled for the given day."""
        return [e for e in self.events if e.day == day]

    def revise(self, from_day: int, new_events: list[ManagementEvent]) -> None:
        """Replace events from from_day onward with new_events."""
        self.events = [e for e in self.events if e.day < from_day] + list(new_events)

    def to_dict(self) -> dict[str, Any]:
        return {"events": [e.to_dict() for e in self.events]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManagementPlan:
        return cls(
            events=[ManagementEvent.from_dict(e) for e in data.get("events", [])]
        )
