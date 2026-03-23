from __future__ import annotations

from pathlib import Path

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import PhenologyStage
from agrogame.plant.roots import RootModule, RootParams, RootState


def test_stage_multiplier_affects_growth() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    params = RootParams(growth_rate_cm_per_day=5.0)
    roots = RootModule(params)
    state1 = RootState(current_depth_cm=10.0)
    inc1 = roots.daily_step(state1, profile, PhenologyStage.VEGETATIVE).depth_inc_cm
    state2 = RootState(current_depth_cm=10.0)
    inc2 = roots.daily_step(state2, profile, PhenologyStage.MATURITY).depth_inc_cm
    assert inc1 > inc2


def test_constraints_reduce_growth_increment() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    roots = RootModule(RootParams(growth_rate_cm_per_day=5.0))
    state = RootState(current_depth_cm=80.0)
    inc = roots.daily_step(
        state,
        profile,
        PhenologyStage.VEGETATIVE,
        constraints={"hardpan_cm": 50.0, "water_table_cm": 70.0},
    ).depth_inc_cm
    assert inc <= 5.0


def test_distribution_skip_when_profile_none() -> None:
    roots = RootModule(RootParams())
    state = RootState(current_depth_cm=10.0)
    _ = roots.daily_step(
        state, None, PhenologyStage.VEGETATIVE  # type: ignore[arg-type]
    )
    # No exception and layer_fractions may remain None
    assert state.current_depth_cm >= 10.0
