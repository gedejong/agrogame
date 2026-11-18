"""Microbial activity survives acid soil across season resets (#553).

On main before #553 the placeholder triangle zeroed microbial activity below pH
5.3, and continuous play takes layer 0 to about pH 5.1 within five years. With
the Rousk, Brookes & Bååth 2009 response, activity at pH 5.1 is about 0.76 of
the pH-6.8 value; this checks the orchestrator delivers that over two seasons.
"""

from __future__ import annotations

from pathlib import Path

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.microbes.events import MicrobialActivityComputed
from agrogame.soil.microbes.responses import EnvironmentalResponses
from agrogame.soil.water.types import DailyDrivers

ACID_PH = 5.1  # layer-0 pH after 5 continuous years on main (#481 refinement)


def test_activity_nonzero_at_ph_5_1_across_two_seasons() -> None:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    maize = crops.get_preset("maize", "netherlands_temperate")
    profile = load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile, crop=maize, latitude_deg=52.0)
    resp = EnvironmentalResponses()
    for season in range(2):
        if season:
            orch.harvest()
            orch.reset_crop(maize)  # clears the bus: subscribe per season
        layer0: list[MicrobialActivityComputed] = []

        def _record(
            ev: MicrobialActivityComputed,
            acc: list[MicrobialActivityComputed] = layer0,
        ) -> None:
            if ev.layer == 0:
                acc.append(ev)

        orch.event_bus.subscribe(MicrobialActivityComputed, _record)
        for _ in range(60):
            orch.chem_state.ph[:] = [ACID_PH] * len(orch.chem_state.ph)
            orch.step_day(
                DailyDrivers(rainfall_mm=3.0),
                tmin_c=10.0,
                tmax_c=22.0,
                shortwave_mj_m2=15.0,
            )
        assert len(layer0) == 60, f"season {season + 1}"
        for ev in layer0:
            assert ev.ph < 5.3  # inside the old triangle's zero zone
            assert ev.activity_index > 0.0, f"season {season + 1}"
            assert 0.70 < resp.ph_modifier(ev.ph) < 0.80
            env = resp.temperature_modifier(ev.temperature_c)
            env *= resp.moisture_modifier(ev.wfps) * resp.ph_modifier(ev.ph)
            # activity = env x priming, priming clamped to [0.5, 3] (biomass.py)
            assert 0.5 * env - 1e-12 <= ev.activity_index <= 3.0 * env + 1e-12
