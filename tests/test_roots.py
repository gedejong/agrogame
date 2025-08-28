from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import PhenologyStage
from agrogame.plant.roots import RootModule, RootParams, RootState
from pathlib import Path


def test_depth_progression_and_cap() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    roots = RootModule(RootParams(max_depth_cm=50.0, growth_rate_cm_per_day=10.0))
    state = RootState(current_depth_cm=5.0)
    for _ in range(10):
        _ = roots.daily_step(state, profile, PhenologyStage.VEGETATIVE)
    assert state.current_depth_cm <= 50.0 + 1e-6


def test_distribution_sums_to_one_and_exponential_surface_bias() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus()
    roots = RootModule(RootParams(distribution="exponential"), event_bus=bus)
    state = RootState(current_depth_cm=60.0)
    _ = roots.daily_step(state, profile, PhenologyStage.VEGETATIVE)
    assert state.layer_fractions is not None
    s = sum(state.layer_fractions or [])
    assert abs(s - 1.0) < 1e-6
    # surface bias: top layer fraction >= deeper layer fraction
    assert (state.layer_fractions or [])[0] >= (
        state.layer_fractions or [0.0, 0.0, 0.0]
    )[-1]


def test_proliferation_bias_increases_rich_layer_fraction() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    roots = RootModule(RootParams(proliferation_strength=0.5))
    state = RootState(current_depth_cm=60.0)
    _ = roots.daily_step(
        state, profile, PhenologyStage.VEGETATIVE, nutrient_signal=[0.0, 1.0, 0.0]
    )
    fracs = state.layer_fractions or []
    assert fracs[1] >= fracs[0] and fracs[1] >= fracs[-1]


def test_turnover_reduces_biomass() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    roots = RootModule(RootParams(turnover_rate_per_day=0.5))
    state = RootState(current_depth_cm=20.0, biomass_g_m2=100.0)
    _ = roots.daily_step(state, profile, PhenologyStage.FLOWERING)
    assert state.biomass_g_m2 < 100.0
