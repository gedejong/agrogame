from __future__ import annotations

from agrogame.sim.orchestrator import build_default_orchestrator


def test_orchestrator_wires_phenology_to_canopy() -> None:
    orch = build_default_orchestrator()
    # LAI should bootstrap after emergence within the first few days
    for _ in range(15):
        orch.step_day(tmin_c=10.0, tmax_c=26.0, par_mj_m2=12.0)
    assert orch.canopy.state.lai > 0.05
