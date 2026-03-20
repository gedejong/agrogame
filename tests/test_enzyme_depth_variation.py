from __future__ import annotations

from pathlib import Path
from agrogame.soil.loader import load_soil_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.water.types import DailyDrivers


def test_enzyme_cost_varies_with_depth() -> None:
    lib = load_soil_presets(Path("data/soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile)

    days = 30
    # Collect cumulative enzyme cost by layer via event wrapping
    totals = [0.0] * len(profile.layers)
    original_emit = orch.event_bus.emit

    def _emit(event: object) -> None:
        try:
            from agrogame.soil.microbes.events import EnzymeProduced

            if isinstance(event, EnzymeProduced):
                if 0 <= event.layer < len(totals):
                    totals[event.layer] += float(event.production_cost_c_kg_ha)
        finally:
            original_emit(event)

    orch.event_bus.emit = _emit  # type: ignore[method-assign]
    for _ in range(days):
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=12,
            tmax_c=22,
            par_mj_m2=14,
            target_ph=6.8,
        )

    # Expect some variation across layers (not perfectly flat)
    assert max(totals) - min(totals) > 0.0
