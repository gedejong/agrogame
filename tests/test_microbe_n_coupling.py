from __future__ import annotations

from pathlib import Path

from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers


def test_microbe_activity_dampens_nitrification() -> None:
    lib = load_soil_presets(Path("data/soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]

    # Baseline orchestrator
    orch_a = FullSimulationOrchestrator(profile)
    # Same profile second orchestrator with forced high fungal fraction and low activity
    orch_b = FullSimulationOrchestrator(profile)
    for layer in orch_b.microbes.state.layers:
        layer.fungal_fraction = 0.9

    days = 60
    for _ in range(days):
        drivers = DailyDrivers(rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0)
        # Baseline
        orch_a.step_day(
            drivers=drivers, tmin_c=18, tmax_c=18, par_mj_m2=10, target_ph=7.0
        )
        # Lower activity: reduce fb adjust and temperature to suppress
        orch_b.microbes.params.fb_adjust_rate = 0.0
        orch_b.step_day(
            drivers=drivers, tmin_c=10, tmax_c=10, par_mj_m2=5, target_ph=6.0
        )

    total_no3_a = sum(orch_a.n_state.no3)
    total_no3_b = sum(orch_b.n_state.no3)
    # With lower activity and high fungal share, nitrification should be lower
    assert total_no3_b <= total_no3_a
