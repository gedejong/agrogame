from __future__ import annotations

from agrogame.events import EventBus
from agrogame.plant.events import WaterStressComputed
from agrogame.soil.phenology import StageChanged, PhenologyStage
from agrogame.soil.canopy import (
    CanopyModule,
    CanopyParams,
    LightIntercepted,
    BiomassAccumulated,
    LAIUpdated,
)
from agrogame.soil.canopy.interception import InterceptionState
from agrogame.soil.canopy.events import CanopyIntercepted, CanopyEvaporated


def test_canopy_daily_step_and_events() -> None:
    bus = EventBus()
    params = CanopyParams(0.6, 3.0, 0.02, 6.0, 0.0)
    canopy = CanopyModule(params, event_bus=bus)
    canopy.state.lai = 1.0

    seen = {
        "light": 0,
        "biomass": 0,
        "lai": 0,
    }

    bus.subscribe(
        LightIntercepted,
        lambda e: seen.__setitem__("light", seen["light"] + 1),
    )
    bus.subscribe(
        BiomassAccumulated,
        lambda e: seen.__setitem__("biomass", seen["biomass"] + 1),
    )
    bus.subscribe(
        LAIUpdated,
        lambda e: seen.__setitem__("lai", seen["lai"] + 1),
    )

    fx = canopy.daily_step(
        incident_par_mj_m2=10.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
    )

    assert fx.intercepted_par_mj_m2 > 0.0
    assert canopy.state.biomass_g_m2 > 0.0
    assert canopy.state.lai > 1.0
    assert seen["light"] == 1 and seen["biomass"] == 1 and seen["lai"] == 1


def test_canopy_senescence_increases_after_grain_fill() -> None:
    bus = EventBus()
    params = CanopyParams(0.6, 3.0, 0.02, 6.0, 0.05)
    canopy = CanopyModule(params, event_bus=bus)
    canopy.state.lai = 2.0

    # Before grain fill, one day with no new biomass
    lai_before = canopy.update_lai(new_leaf_biomass_g_m2=0.0)

    # Trigger grain fill stage
    bus.emit(
        StageChanged(
            from_stage=PhenologyStage.VEGETATIVE,
            to_stage=PhenologyStage.GRAIN_FILL,
            at_gdd=900,
        )
    )

    # After grain fill, senescence multiplier applies; expect larger decrease
    canopy.state.lai = 2.0
    lai_after = canopy.update_lai(new_leaf_biomass_g_m2=0.0)

    assert (2.0 - lai_after) > (2.0 - lai_before)


def test_lai_bootstraps_on_emergence() -> None:
    bus = EventBus()
    params = CanopyParams(0.6, 3.0, 0.02, 6.0, 0.01)
    canopy = CanopyModule(params, event_bus=bus)
    assert canopy.state.lai == 0.0
    bus.emit(
        StageChanged(
            from_stage=PhenologyStage.PLANTED,
            to_stage=PhenologyStage.EMERGED,
            at_gdd=120.0,
        )
    )
    assert canopy.state.lai >= 0.1


def test_water_stress_event_emitted() -> None:
    bus = EventBus()
    seen: dict[str, float | None] = {"stress": None}
    bus.subscribe(WaterStressComputed, lambda e: seen.__setitem__("stress", e.stress))
    bus.emit(WaterStressComputed(supply_mm=2.0, demand_mm=4.0, stress=0.5))
    assert seen["stress"] == 0.5


def test_interception_events_and_mass_balance() -> None:
    bus = EventBus()
    seen = {"int": 0.0, "evap": 0.0}
    bus.subscribe(
        CanopyIntercepted, lambda e: seen.__setitem__("int", seen["int"] + e.amount_mm)
    )
    bus.subscribe(
        CanopyEvaporated, lambda e: seen.__setitem__("evap", seen["evap"] + e.amount_mm)
    )

    istate = InterceptionState(capacity_coef_mm_per_lai=0.5, event_bus=bus)
    lai = 2.0
    rain = 1.0
    intercepted, throughfall = istate.intercept(lai, rain)
    assert intercepted == rain and throughfall == 0.0
    taken = istate.evaporate(0.6)
    assert 0.5 <= taken <= 0.6
    # Events match
    assert abs(seen["int"] - intercepted) < 1e-9
    assert abs(seen["evap"] - taken) < 1e-9
    # Canopy store balance
    assert abs(istate.store_mm - (intercepted - taken)) < 1e-9
