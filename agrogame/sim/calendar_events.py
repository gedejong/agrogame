"""Back-compat shim — DayTick lives at agrogame.events.calendar (#300).

New code should import from ``agrogame.events.calendar`` directly. This
module re-exports the names so external scripts and notebooks keep
working. Slated for removal once external consumers have migrated.
"""

from __future__ import annotations

from agrogame.events.calendar import DayTick, Phase

__all__ = ["DayTick", "Phase"]
