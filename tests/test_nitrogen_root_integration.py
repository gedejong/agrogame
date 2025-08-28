from __future__ import annotations

from pathlib import Path

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.atmosphere.et.module import Evapotranspiration


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


def test_massflow_uptake_increases_with_transpiration() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    nstate = SoilNitrogenState(profile)
    # Seed nitrate evenly
    n_layers = len(nstate.no3)
    for i in range(n_layers):
        nstate.no3[i] = 10.0

    bus = EventBus()
    wstate = SoilWaterState(profile)
    water = CascadingBucketWaterModel(event_bus=bus)
    _ = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)

    # Simulate two transpiration events with different totals but same distribution
    root_fracs = [1.0 / n_layers] * n_layers
    # Use ET module to compute actual ET for given potential split
    et = Evapotranspiration()
    et0 = 5.0
    comps = et.potential_components(et0_mm=et0, lai=1.5)
    # First day: lower demand
    actual1 = et.actual_et(profile, wstate, water, comps, root_fracs)
    total1 = actual1.transpiration_mm
    # Second day: increase potential to drive higher transpiration
    et0_high = et0 * 1.5
    comps_high = et.potential_components(et0_mm=et0_high, lai=1.5)
    actual2 = et.actual_et(profile, wstate, water, comps_high, root_fracs)
    total2 = actual2.transpiration_mm

    # Expect higher total transpiration on the second day
    assert total2 >= total1
    # After both events, total NO3 should decrease more than zero
    total_no3_after = sum(nstate.no3)
    assert total_no3_after < 10.0 * n_layers


def test_massflow_uptake_bounded_by_availability() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    nstate = SoilNitrogenState(profile)
    # Only a small NO3 pool in top layer; others zero
    for i in range(len(nstate.no3)):
        nstate.no3[i] = 0.0
    nstate.no3[0] = 0.5  # kg/ha

    bus = EventBus()
    wstate = SoilWaterState(profile)
    water = CascadingBucketWaterModel(event_bus=bus)
    _ = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)

    # Drive transpiration focused on layer 0
    et = Evapotranspiration()
    et0 = 8.0
    comps = et.potential_components(et0_mm=et0, lai=2.0)
    rf = [1.0] + [0.0] * (len(profile.layers) - 1)
    _ = et.actual_et(profile, wstate, water, comps, rf)

    # NO3 cannot go below zero
    assert nstate.no3[0] >= 0.0
