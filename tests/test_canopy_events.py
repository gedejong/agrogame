from __future__ import annotations

from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.phenology import StageChanged, PhenologyStage
from agrogame.soil.canopy import (
    CanopyModule,
    CanopyParams,
    LightIntercepted,
    BiomassAccumulated,
    LAIUpdated,
)


def test_canopy_daily_step_and_events():
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


def test_canopy_senescence_increases_after_grain_fill():
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


def test_lai_bootstraps_on_emergence():
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
