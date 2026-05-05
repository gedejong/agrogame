from __future__ import annotations

from datetime import date

from agrogame.events import EventBus
from agrogame.sim.calendar import Calendar
from agrogame.events.calendar import DayTick
from agrogame.soil.water.types import DailyDrivers


def test_calendar_emits_phased_daytick_in_order() -> None:
    bus = EventBus()
    cal = Calendar(bus)
    seen: list[str] = []
    bus.subscribe(DayTick, lambda e: seen.append(e.phase))

    cal.tick(
        sim_date=date(2025, 1, 1),
        drivers=DailyDrivers(rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0),
        target_ph=6.8,
    )

    assert seen == [
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
