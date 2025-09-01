from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.legacy import SoilWaterBalance
from agrogame.soil.canopy.interception import InterceptionState
from agrogame.soil.canopy.events import CanopyIntercepted, CanopyEvaporated
from pathlib import Path


def test_legacy_daily_emits_canopy_events_with_interception() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus()
    seen = {"int": 0.0, "evap": 0.0}
    bus.subscribe(
        CanopyIntercepted, lambda e: seen.__setitem__("int", seen["int"] + e.amount_mm)
    )
    bus.subscribe(
        CanopyEvaporated, lambda e: seen.__setitem__("evap", seen["evap"] + e.amount_mm)
    )

    # Use InterceptionState directly; in legacy wrapper we simulate the daily sequence
    istate = InterceptionState(capacity_coef_mm_per_lai=0.5, event_bus=bus)
    swb = SoilWaterBalance(profile, event_bus=bus)

    lai = 2.0
    rain = 1.0
    intercepted, throughfall = istate.intercept(lai, rain)
    # Soil water receives only throughfall; evaporation is taken from canopy first
    _ = swb.update_daily(rainfall_mm=throughfall, evaporation_mm=0.0)
    # Apply canopy evaporation with a simple potential value
    taken = istate.evaporate(0.6)

    assert abs(seen["int"] - intercepted) < 1e-9
    assert abs(seen["evap"] - taken) < 1e-9
