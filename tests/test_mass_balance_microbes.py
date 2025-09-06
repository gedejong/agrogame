from __future__ import annotations

from pathlib import Path
from agrogame.soil.loader import load_soil_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.water.types import DailyDrivers


def test_microbe_cn_mass_balance_stability() -> None:
    lib = load_soil_presets(Path("data/soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile)

    def totals() -> tuple[float, float]:
        total_c = sum(ls.c_kg_ha for ls in orch.microbes.state.layers)
        total_n = sum(ls.n_kg_ha for ls in orch.microbes.state.layers)
        return total_c, total_n

    c0, n0 = totals()
    days = 120
    for _ in range(days):
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=10,
            tmax_c=20,
            par_mj_m2=12,
            target_ph=6.8,
        )
    c1, n1 = totals()

    # We do not enforce closed mass balance (inputs from SOM placeholder),
    # but large drifts indicate instability. Allow moderate change.
    assert abs(c1 - c0) < 200.0
    assert abs(n1 - n0) < 50.0
