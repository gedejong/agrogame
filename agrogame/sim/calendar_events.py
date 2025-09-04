from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

from agrogame.events import BaseEvent
from agrogame.soil.water.types import DailyDrivers


Phase = Literal[
    "day_start",
    "chemistry",
    "water",
    "plant_structure",
    "et",
    "nutrients",
    "canopy",
    "day_end",
]


@dataclass(frozen=True)
class DayTick(BaseEvent):
    sim_date: date
    phase: Phase
    drivers: Optional[DailyDrivers] = None
    target_ph: Optional[float] = None
