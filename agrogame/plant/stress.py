from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StressFactors:
    """Shared stress factors for modules that react to water/N stress.

    Values are in 0..1, where lower means more stress.
    """

    water: float = 1.0
    nitrogen: float = 1.0
