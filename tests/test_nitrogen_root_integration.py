from __future__ import annotations

from pathlib import Path

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.water.state import SoilWaterState


def test_nitrogen_cycle_uses_root_fractions_for_uptake() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    nstate = SoilNitrogenState(profile)
    # Seed nitrate to layer 0 only
    for i in range(len(nstate.no3)):
        nstate.no3[i] = 0.0
    nstate.no3[0] = 10.0

    bus = EventBus()
    cycle = NitrogenCycle(
        bus, nstate, water_state=SoilWaterState(profile), profile=profile
    )

    uptake = cycle.daily_step(
        temperature_c=20.0,
        plant_demand_kg_ha=5.0,
        root_fractions=[1.0, 0.0, 0.0],
    )
    assert uptake.plant_uptake_kg_ha <= 5.0
    # After uptake, most extraction comes from layer 0 where roots are
    assert nstate.no3[0] < 10.0


def test_nitrogen_cycle_uses_cached_root_fractions_when_none_passed() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    nstate = SoilNitrogenState(profile)
    # Seed nitrate to layer 1 only
    for i in range(len(nstate.no3)):
        nstate.no3[i] = 0.0
    nstate.no3[1] = 8.0

    bus = EventBus()
    cycle = NitrogenCycle(
        bus, nstate, water_state=SoilWaterState(profile), profile=profile
    )

    # Cache root fractions via event (favor layer 1)
    from agrogame.plant.roots.events import RootDistributionUpdated

    bus.emit(RootDistributionUpdated(fractions=(0.0, 1.0, 0.0)))

    _ = cycle.daily_step(temperature_c=20.0, plant_demand_kg_ha=4.0)
    assert nstate.no3[1] < 8.0
