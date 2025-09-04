from __future__ import annotations

from datetime import date

from agrogame.events import EventBus
from agrogame.soil.water.types import DailyDrivers
from .calendar_events import DayTick, Phase


class Calendar:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def tick(
        self,
        sim_date: date,
        drivers: DailyDrivers,
        target_ph: float,
        phases: list[Phase] | None = None,
        *,
        tmin_c: float | None = None,
        tmax_c: float | None = None,
        par_mj_m2: float | None = None,
    ) -> None:
        emit = self.event_bus.emit
        order: list[Phase] = (
            [
                "day_start",
                "chemistry",
                "water",
                "plant_structure",
                "et",
                "nutrients",
                "canopy",
                "day_end",
            ]
            if phases is None
            else phases
        )
        for ph in order:
            emit(
                DayTick(
                    sim_date=sim_date,
                    phase=ph,
                    drivers=drivers if ph in ("water", "et") else None,
                    target_ph=target_ph,
                    tmin_c=tmin_c,
                    tmax_c=tmax_c,
                    par_mj_m2=par_mj_m2,
                )
            )
