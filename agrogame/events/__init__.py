"""Event-bus primitives shared across simulation modules.

Docs: https://github.com/gedejong/agrogame/blob/main/docs/events.md
"""

from __future__ import annotations

from .base import BaseEvent
from .bus import EventBus, EventHandlerError
from agrogame.config.events import ConfigReloaded

__all__ = [
    "BaseEvent",
    "EventBus",
    "EventHandlerError",
    "ConfigReloaded",
]
