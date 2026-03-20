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


def test_massflow_decreases_with_water_stress() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    nstate = SoilNitrogenState(profile)
    for i in range(len(nstate.no3)):
        nstate.no3[i] = 20.0
    bus = EventBus()
    wstate = SoilWaterState(profile)
    water = CascadingBucketWaterModel(event_bus=bus)
    _ = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)

    et = Evapotranspiration()
    rf = [1.0 / len(profile.layers)] * len(profile.layers)

    def run_once(et0: float) -> tuple[float, float]:
        comps = et.potential_components(et0_mm=et0, lai=2.0)
        no3_before = sum(nstate.no3)
        actual = et.actual_et(profile, wstate, water, comps, rf)
        uptake = max(0.0, no3_before - sum(nstate.no3))
        return actual.transpiration_mm, uptake

    t1, u1 = run_once(5.0)
    t2, u2 = run_once(2.5)  # lower ET0
    assert t2 <= t1 + 1e-6
    assert u2 <= u1 + 1e-6


def test_transpiration_by_layer_event_integrity() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus()
    events: list = []
    from agrogame.soil.water.events import TranspirationByLayer

    bus.subscribe(TranspirationByLayer, lambda e: events.append(e))
    wstate = SoilWaterState(profile)
    water = CascadingBucketWaterModel(event_bus=bus)
    # Set adequate water above wilting in first two layers
    for i, layer in enumerate(profile.layers[:2]):
        storage = (layer.wilting_point + 0.05) * layer.depth_cm * 10.0
        wstate.set_layer_storage_mm(profile, i, storage)
    rf = [0.5, 0.5] + [0.0] * (len(profile.layers) - 2)
    taken = water.extract_transpiration_by_roots(profile, wstate, 4.0, rf)
    assert events, "No TranspirationByLayer event captured"
    evt = events[-1]
    assert abs(sum(evt.amounts_mm) - evt.total_mm) < 1e-6
    assert abs(evt.total_mm - taken) < 1e-6


def test_zero_et_and_zero_no3_yield_zero_uptake() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    nstate = SoilNitrogenState(profile)
    for i in range(len(nstate.no3)):
        nstate.no3[i] = 0.0
    bus = EventBus()
    wstate = SoilWaterState(profile)
    water = CascadingBucketWaterModel(event_bus=bus)
    _ = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)
    et = Evapotranspiration()
    rf = [1.0 / len(profile.layers)] * len(profile.layers)
    comps = et.potential_components(et0_mm=0.0, lai=1.0)
    no3_before = sum(nstate.no3)
    _ = et.actual_et(profile, wstate, water, comps, rf)
    assert sum(nstate.no3) == no3_before
