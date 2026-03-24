from __future__ import annotations

from datetime import date

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.phenology import (
    PhenologyModule,
    CropPhenologyParams,
    GrowthStageThresholds,
)
from agrogame.soil.phenology.runtime import PhenologyRuntime


def test_runtime_uses_computed_photoperiod() -> None:
    """PhenologyRuntime should compute photoperiod from latitude, not use 12.0."""
    bus = EventBus()
    pheno = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
            photoperiod_sensitivity=0.5,
        ),
        event_bus=bus,
    )
    # Summer day at 60°N should have long photoperiod (>16h)
    runtime = PhenologyRuntime(bus, pheno, latitude_deg=60.0)
    bus.emit(
        DayTick(
            sim_date=date(2024, 6, 21),
            phase="plant_structure",
            tmin_c=10.0,
            tmax_c=20.0,
        )
    )
    gdd_summer = pheno.state.accumulated_gdd

    # Reset and try winter day — shorter photoperiod should yield different GDD
    pheno2 = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
            photoperiod_sensitivity=0.5,
        ),
        event_bus=bus,
    )
    runtime2 = PhenologyRuntime(bus, pheno2, latitude_deg=60.0)
    bus.emit(
        DayTick(
            sim_date=date(2024, 12, 21),
            phase="plant_structure",
            tmin_c=10.0,
            tmax_c=20.0,
        )
    )
    gdd_winter = pheno2.state.accumulated_gdd

    # With photoperiod sensitivity, summer GDD should differ from winter
    assert gdd_summer != gdd_winter
    _ = runtime, runtime2  # keep references


def test_runtime_default_latitude() -> None:
    """Default latitude should be 52.0 (Netherlands)."""
    bus = EventBus()
    pheno = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        ),
        event_bus=bus,
    )
    runtime = PhenologyRuntime(bus, pheno)
    assert runtime.latitude_deg == 52.0
