from __future__ import annotations

from datetime import date

from agrogame.sim.builder import SimulationBuilder
from agrogame.soil.loader import load_soil_presets
from pathlib import Path
from agrogame.soil.water.types import DailyDrivers


def test_builder_creates_app_and_calendar_ticks() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    app = SimulationBuilder().build(profile)

    # Smoke test: tick one day
    app.calendar.tick(
        sim_date=date(2025, 1, 1),
        drivers=DailyDrivers(rainfall_mm=1.0, irrigation_mm=0.0, evaporation_mm=1.0),
        target_ph=6.8,
    )
