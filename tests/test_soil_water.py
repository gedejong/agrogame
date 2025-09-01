from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.loader import load_soil_presets as _load
from agrogame.soil.water import (
    CascadingBucketWaterModel,
    DailyDrivers,
    SoilWaterState,
)
from agrogame.soil.canopy.interception import InterceptionState
from agrogame.events import EventBus
from agrogame.soil.water import SoilWaterBalance
from agrogame.soil.water.events import CanopyIntercepted, CanopyEvaporated


def _make_state(lib_id: str = "loam_temperate"):
    lib = _load(Path("soils/presets.yaml"))
    profile = lib.soils[lib_id]
    state = SoilWaterState(profile)
    return profile, state


def test_mass_balance_day() -> None:
    profile, state = _make_state()
    model = CascadingBucketWaterModel()
    flux = model.update_daily(
        profile,
        state,
        DailyDrivers(rainfall_mm=10.0, irrigation_mm=0.0, evaporation_mm=2.0),
    )
    inputs = 10.0
    outputs = flux.runoff_mm + flux.deep_drainage_mm + flux.evap_mm
    assert abs((inputs - outputs) - flux.storage_change_mm) < 1e-6


def test_permeability_ordering() -> None:
    sand_prof, sand_state = _make_state("sandy_arid")
    clay_prof, clay_state = _make_state("clay_temperate")
    model = CascadingBucketWaterModel()

    sand_flux = model.update_daily(
        sand_prof, sand_state, DailyDrivers(rainfall_mm=40.0, evaporation_mm=2.0)
    )
    clay_flux = model.update_daily(
        clay_prof, clay_state, DailyDrivers(rainfall_mm=40.0, evaporation_mm=2.0)
    )

    assert sand_flux.runoff_mm <= clay_flux.runoff_mm + 1e-6
    assert sand_flux.deep_drainage_mm >= clay_flux.deep_drainage_mm - 1e-6


def test_event_emission() -> None:
    profile, state = _make_state("sandy_arid")
    bus = EventBus(debug_mode=True)
    seen = {"runoff": 0.0, "evap": 0.0, "infil_calls": 0, "drain_calls": 0}

    from agrogame.soil.water import (
        RunoffGenerated,
        EvaporationTaken,
        WaterInfiltrated,
        WaterDrained,
    )

    bus.subscribe(RunoffGenerated, lambda e: seen.__setitem__("runoff", e.amount_mm))
    bus.subscribe(EvaporationTaken, lambda e: seen.__setitem__("evap", e.amount_mm))
    bus.subscribe(
        WaterInfiltrated,
        lambda e: seen.__setitem__("infil_calls", seen["infil_calls"] + 1),
    )
    bus.subscribe(
        WaterDrained, lambda e: seen.__setitem__("drain_calls", seen["drain_calls"] + 1)
    )

    model = CascadingBucketWaterModel(event_bus=bus)
    _ = model.update_daily(
        profile, state, DailyDrivers(rainfall_mm=50.0, evaporation_mm=1.0)
    )

    assert seen["evap"] >= 0.0
    assert seen["infil_calls"] >= 1


def test_water_balance_closure() -> None:
    lib = _load(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    swb = SoilWaterBalance(profile)

    # Baseline storage
    runoff, deep, dS = swb.update_daily(
        rainfall_mm=10.0, irrigation_mm=0.0, evaporation_mm=2.0
    )
    # Inputs - outputs ≈ dS (use actual evaporation taken)
    inputs = 10.0
    outputs = runoff + deep + swb.last_evap_mm
    assert abs((inputs - outputs) - dS) < 1e-6


def test_day_mass_balance_with_interception_events() -> None:
    lib = _load(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus(debug_mode=True)
    seen = {"int": 0.0, "cevap": 0.0}
    bus.subscribe(CanopyIntercepted, lambda e: seen.__setitem__("int", e.amount_mm))
    bus.subscribe(CanopyEvaporated, lambda e: seen.__setitem__("cevap", e.amount_mm))

    swb = SoilWaterBalance(profile, event_bus=bus, interception=InterceptionState(0.5))
    rain = 5.0
    evap = 2.0
    runoff, deep, dS = swb.update_daily(rainfall_mm=rain, evaporation_mm=evap, lai=3.0)
    # Partitioning sanity and full mass balance including evaporation
    throughfall = rain - seen["int"]
    assert abs((seen["int"] + throughfall) - rain) < 1e-9
    total_evap = swb.last_evap_mm  # canopy + soil evap aggregated in wrapper
    assert abs(rain - (total_evap + runoff + deep + dS)) < 1e-6
    assert total_evap >= seen["cevap"]


def test_cascade_downward() -> None:
    lib = _load(Path("soils/presets.yaml"))
    profile = lib.soils["sandy_arid"]
    swb = SoilWaterBalance(profile)
    # Large rainfall should generate runoff and/or deep drainage but not break
    runoff, deep, _ = swb.update_daily(rainfall_mm=80.0)
    assert runoff >= 0.0
    assert deep >= 0.0


def test_permeability_comparison() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    sand = lib.soils["sandy_arid"]
    clay = lib.soils["clay_temperate"]

    # Same rainfall across profiles
    rain = 40.0
    evapo = 2.0

    swb_sand = SoilWaterBalance(sand)
    swb_clay = SoilWaterBalance(clay)

    runoff_sand, deep_sand, _ = swb_sand.update_daily(
        rainfall_mm=rain, evaporation_mm=evapo
    )
    runoff_clay, deep_clay, _ = swb_clay.update_daily(
        rainfall_mm=rain, evaporation_mm=evapo
    )

    # Expect sand to have less runoff and more deep drainage than clay (more permeable)
    assert runoff_sand <= runoff_clay + 1e-6
    assert deep_sand >= deep_clay - 1e-6


def _simulate_days(
    profile_name: str, days: int = 30, rain_mm: float = 5.0, evap_mm: float = 2.0
):
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    swb = SoilWaterBalance(profile)
    cum_in = 0.0
    cum_out = 0.0
    cum_dS = 0.0
    for _ in range(days):
        runoff, deep, dS = swb.update_daily(
            rainfall_mm=rain_mm, irrigation_mm=0.0, evaporation_mm=evap_mm
        )
        cum_in += rain_mm
        cum_out += runoff + deep + swb.last_evap_mm
        cum_dS += dS
    return cum_in, cum_out, cum_dS


def test_mass_balance_multi_day() -> None:
    cum_in, cum_out, cum_dS = _simulate_days(
        "loam_temperate", days=60, rain_mm=6.0, evap_mm=2.5
    )
    assert abs((cum_in - cum_out) - cum_dS) < 1e-6


@settings(max_examples=50, deadline=None)
@given(
    rain=st.floats(min_value=0.0, max_value=50.0),
    evap=st.floats(min_value=0.0, max_value=10.0),
    days=st.integers(min_value=1, max_value=30),
)
def test_property_mass_balance(rain: float, evap: float, days: int) -> None:
    # Property: for any non-negative inputs, total mass balance holds within tolerance
    cum_in, cum_out, cum_dS = _simulate_days(
        "sandy_loam_temperate", days=days, rain_mm=rain, evap_mm=evap
    )
    assert abs((cum_in - cum_out) - cum_dS) < 1e-6


def test_texture_order_runoff_and_drainage() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    textures = [
        "sandy_arid",
        "sandy_loam_temperate",
        "loam_temperate",
        "clay_loam_temperate",
        "clay_temperate",
    ]
    rain = 30.0
    evapo = 1.0
    runoffs = []
    drains = []
    for name in textures:
        swb = SoilWaterBalance(lib.soils[name])
        runoff, deep, _ = swb.update_daily(rainfall_mm=rain, evaporation_mm=evapo)
        runoffs.append(runoff)
        drains.append(deep)
    # Expect non-decreasing runoff with heavier textures
    # and non-increasing deep drainage
    assert all(a <= b + 1e-6 for a, b in zip(runoffs, runoffs[1:]))
    assert all(a >= b - 1e-6 for a, b in zip(drains, drains[1:]))


def test_interception_fills_and_evaporates_before_soil() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    state = SoilWaterState(profile)
    model = CascadingBucketWaterModel()
    istate = InterceptionState(capacity_coef_mm_per_lai=0.5)
    lai = 2.0
    rain = 1.0
    intercepted, throughfall = istate.intercept(lai, rain)
    assert intercepted == rain and throughfall == 0.0
    taken = istate.evaporate(0.6)
    assert 0.5 <= taken <= 0.6
    fx = model.update_daily(
        profile, state, DailyDrivers(rainfall_mm=0.0, evaporation_mm=0.0)
    )
    assert fx.evap_mm >= 0.0
