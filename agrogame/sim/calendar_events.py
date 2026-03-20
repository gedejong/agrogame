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
    tmin_c: Optional[float] = None
    tmax_c: Optional[float] = None
    par_mj_m2: Optional[float] = None
    plant_n_demand_kg_ha: Optional[float] = None
    plant_p_demand_kg_ha: Optional[float] = None
