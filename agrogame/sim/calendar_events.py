from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from agrogame.events import BaseEvent
from agrogame.soil.water.types import DailyDrivers


Phase = Literal[
    "day_start",
    "chemistry",
    "water",
    "redox",
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
    drivers: DailyDrivers | None = None
    target_ph: float | None = None
    tmin_c: float | None = None
    tmax_c: float | None = None
    par_mj_m2: float | None = None
    plant_n_demand_kg_ha: float | None = None
    plant_p_demand_kg_ha: float | None = None
