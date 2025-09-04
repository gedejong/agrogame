from __future__ import annotations

from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from pathlib import Path
from agrogame.soil.water.types import DailyDrivers


def test_full_orchestrator_advances_and_emits() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile)

    # Advance a few days with mild rain
    for _ in range(5):
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=2.0, irrigation_mm=0.0, evaporation_mm=1.0
            ),
            tmin_c=10.0,
            tmax_c=22.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )

    # Sanity checks on state coupling
    assert sum(orch.p_state.available_p) >= 0.0
    assert sum(orch.n_state.no3) >= 0.0
    # Root module should have updated once (depth > 0 or fractions set)
    assert orch.root_state.current_depth_cm >= 0.0
