from __future__ import annotations

import time
from pathlib import Path

import pytest

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water import (
    CascadingBucketWaterModel,
    DailyDrivers,
    SoilWaterState,
)
from agrogame.events import EventBus


# Skipped by default to avoid impacting CI durations
pytestmark = pytest.mark.skip(reason="Performance test; run locally when needed")


def test_event_bus_overhead_benchmark() -> None:
    """Micro-benchmark to estimate overhead of the event bus.

    This is intentionally skipped in CI. Run locally to observe timings.
    """
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]

    iterations = 500
    drivers = DailyDrivers(rainfall_mm=5.0, evaporation_mm=2.0)

    # Baseline without event bus
    state_no_bus = SoilWaterState(profile)
    model_no_bus = CascadingBucketWaterModel()
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = model_no_bus.update_daily(profile, state_no_bus, drivers)
    no_bus_ms = (time.perf_counter() - t0) * 1000.0

    # With event bus (no subscribers)
    state_with_bus = SoilWaterState(profile)
    model_with_bus = CascadingBucketWaterModel(event_bus=EventBus())
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = model_with_bus.update_daily(profile, state_with_bus, drivers)
    with_bus_ms = (time.perf_counter() - t0) * 1000.0

    overhead_pct = (with_bus_ms - no_bus_ms) / max(no_bus_ms, 1e-9) * 100.0
    # Printed for human inspection when run locally
    print(
        f"iterations={iterations} no_bus_ms={no_bus_ms:.2f} "
        f"with_bus_ms={with_bus_ms:.2f} overhead_pct={overhead_pct:.1f}%"
    )
