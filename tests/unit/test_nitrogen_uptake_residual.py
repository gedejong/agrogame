"""Plant N uptake stops at the CERES residual in each rooted layer (#694).

CERES-Maize caps a layer's uptake at ``SNO3 - 0.25/KG2PPM`` and
``SNH4 - 0.5/KG2PPM``, with ``KG2PPM = 10/(BD*DLAYR)`` (DSSAT-CSM v4.8.6.0
``MZ_NUPTAK.for:211-214``; Jones et al. 2003, Eur. J. Agron. 18:235-265). In
kg N/ha per layer that is ``r3 = 0.25 x BD x depth_cm / 10`` and
``r4 = 0.5 x BD x depth_cm / 10``. Only uptake is floored, as in DSSAT.
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from agrogame.soil.nitrogen import NitrogenCycle, NitrogenRateParams, SoilNitrogenState
from agrogame.soil.nitrogen.constants import N_KG_PER_KMOL
from agrogame.soil.water.events import WaterDrained
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

ROOTS_TOP = [1.0, 0.0, 0.0]
# ``pool - (pool - r)`` can land one ulp under ``r``: the floor holds to rounding.
_ULP = 1e-12


def _soil(key: str) -> SoilProfile:
    return load_soil_presets(Path("soils/presets.yaml")).soils[key]


def _cycle(
    no3: list[float],
    nh4: list[float],
    *,
    key: str = "loam_temperate",
    with_profile: bool = True,
    params: NitrogenRateParams | None = None,
) -> NitrogenCycle:
    profile = _soil(key)
    state = SoilNitrogenState(profile)
    state.no3, state.nh4 = list(no3), list(nh4)
    state.organic_n = [0.0] * len(no3)
    prof = cast(Any, profile) if with_profile else None
    return NitrogenCycle(EventBus(), state, profile=prof, params=params)


# --- AC1: the residual ------------------------------------------------------


def test_loam_topsoil_gives_up_only_what_lies_above_its_residual() -> None:
    """loam_temperate layer 0 (25 cm, BD 1.45): r3 0.90625, r4 1.8125 kg N/ha."""
    cycle = _cycle([5.0, 0.0, 0.0], [3.0, 0.0, 0.0])
    assert cycle._take_up_plant(100.0, ROOTS_TOP) == 5.28125  # 4.09375 + 1.1875
    assert cycle.state.no3[0] == 0.90625
    assert cycle.state.nh4[0] == 1.8125
    # Proton accrual is unchanged: -1 per NO3-N and +1 per NH4-N taken up.
    assert cycle.pending_proton_load_kmol_ha[0] == pytest.approx(
        (-4.09375 + 1.1875) / N_KG_PER_KMOL, abs=1e-15
    )


def test_sandy_topsoil_residual() -> None:
    """sandy_temperate layer 0 (25 cm, BD 1.6): r3 1.0, r4 2.0 kg N/ha."""
    cycle = _cycle([0.0] * 3, [0.0] * 3, key="sandy_temperate")
    assert cycle._uptake_residual_no3[0] == pytest.approx(1.0, abs=1e-12)
    assert cycle._uptake_residual_nh4[0] == pytest.approx(2.0, abs=1e-12)


def test_no_layer_is_drawn_below_its_residual_or_raised() -> None:
    rng = random.Random(694)
    for _ in range(300):
        no3 = [rng.uniform(0.0, 6.0) for _ in range(3)]
        nh4 = [rng.uniform(0.0, 6.0) for _ in range(3)]
        roots = [rng.choice([0.0, rng.random()]) for _ in range(3)]
        cycle = _cycle(no3, nh4)
        taken = cycle._take_up_plant(rng.uniform(0.0, 50.0), roots)
        assert taken >= 0.0
        for i in range(3):
            r3, r4 = cycle._uptake_residual_no3[i], cycle._uptake_residual_nh4[i]
            assert min(no3[i], r3) - _ULP <= cycle.state.no3[i] <= no3[i]
            assert min(nh4[i], r4) - _ULP <= cycle.state.nh4[i] <= nh4[i]
        removed = sum(no3) + sum(nh4) - sum(cycle.state.no3) - sum(cycle.state.nh4)
        assert taken == pytest.approx(removed, abs=1e-12)


# --- AC2: edge cases ---------------------------------------------------------


def test_a_form_below_its_residual_gives_nothing_and_stays() -> None:
    """NO3 0.5 < r3 0.90625: the demand falls on NH4, which stops at r4."""
    cycle = _cycle([0.5, 0.0, 0.0], [3.0, 0.0, 0.0])
    assert cycle._take_up_plant(10.0, ROOTS_TOP) == pytest.approx(3.0 - 1.8125)
    assert cycle.state.no3[0] == 0.5
    assert cycle.state.nh4[0] == 1.8125
    below = _cycle([0.5, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert below._take_up_plant(10.0, ROOTS_TOP) == 0.0
    assert (below.state.no3[0], below.state.nh4[0]) == (0.5, 1.0)


@pytest.mark.parametrize("demand", [0.0, -5.0])
def test_no_demand_takes_nothing(demand: float) -> None:
    cycle = _cycle([5.0, 0.0, 0.0], [3.0, 0.0, 0.0])
    assert cycle._take_up_plant(demand, ROOTS_TOP) == 0.0
    assert (cycle.state.no3[0], cycle.state.nh4[0]) == (5.0, 3.0)


def test_a_cycle_without_a_profile_has_no_residual() -> None:
    cycle = _cycle([5.0, 0.0, 0.0], [3.0, 0.0, 0.0], with_profile=False)
    assert cycle._uptake_residual_no3 == cycle._uptake_residual_nh4 == [0.0] * 3
    assert cycle._take_up_plant(100.0, ROOTS_TOP) == 8.0
    assert (cycle.state.no3[0], cycle.state.nh4[0]) == (0.0, 0.0)


# --- AC3: unchanged above the residual ----------------------------------------


def test_above_the_residual_uptake_matches_a_cycle_without_one() -> None:
    roots = [0.5, 0.3, 0.2]
    no3, nh4 = [20.0, 20.0, 20.0], [10.0, 10.0, 10.0]
    floored = _cycle(no3, nh4)
    free = _cycle(no3, nh4, with_profile=False)
    assert floored._take_up_plant(12.0, roots) == free._take_up_plant(12.0, roots)
    assert floored.state.no3 == free.state.no3
    assert floored.state.nh4 == free.state.nh4
    assert floored.pending_proton_load_kmol_ha == free.pending_proton_load_kmol_ha
    for i in range(3):  # the floor did not bind
        assert floored.state.no3[i] > floored._uptake_residual_no3[i]


def test_a_layer_shortfall_is_not_redistributed() -> None:
    """Layer 0 sits at its residual; layer 1 gives its own half and no more."""
    cycle = _cycle([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    cycle.state.no3[0] = cycle._uptake_residual_no3[0]
    cycle.state.nh4[0] = cycle._uptake_residual_nh4[0]
    cycle.state.no3[1] = 20.0
    assert cycle._take_up_plant(10.0, [0.5, 0.5, 0.0]) == pytest.approx(5.0)
    assert cycle.state.no3[1] == pytest.approx(15.0)


def test_other_sinks_are_not_floored() -> None:
    """Nitrification, denitrification, leaching and volatilisation can empty a pool."""
    rates = NitrogenRateParams(
        nitrification_base_rate=100.0,
        nitrification_max_rate=1.0,
        denitrification_base_rate=100.0,
        volatilization_base_rate=100.0,
        volatilization_max_rate=1.0,
    )
    cycle = _cycle([1.0, 0.5, 0.0], [1.0, 0.0, 0.0], params=rates)
    cycle._env.fungal_fraction_by_layer = [0.0] * 3
    assert cycle._nitrify_layer(0, 1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0)
    assert cycle.state.nh4[0] == 0.0
    assert cycle._denitrify_layer(0, 1.0, 1.0) == pytest.approx(2.0)
    assert cycle.state.no3[0] == 0.0
    cycle.event_bus.emit(WaterDrained(from_layer=1, to_layer=3, amount_mm=1000.0))
    assert cycle.state.no3[1] == 0.0
    cycle.apply_urea(0, 1.0)
    cycle.state.nh4[0] = cycle.state.surface_fertilizer_nh4_kg_ha = 1.0
    assert cycle._volatilize_surface(1.0, 9.0) == pytest.approx(1.0)
    assert cycle.state.nh4[0] == 0.0


# --- Two seasons through the orchestrator -------------------------------------


def test_two_maize_seasons_never_draw_a_layer_below_its_residual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NL maize on loam_temperate, sown twice with ``reset_crop`` between.

    Every uptake call, in both seasons, leaves each layer at or above its
    residual (or untouched if it was already below), and the unfertilised
    profile keeps more than half its 1 m residual on every season day.
    """
    original = NitrogenCycle._take_up_plant
    calls: list[float] = []

    def checked(self: NitrogenCycle, demand: float, roots: list[float]) -> float:
        no3, nh4 = list(self.state.no3), list(self.state.nh4)
        taken = original(self, demand, roots)
        for i in range(len(no3)):
            r3, r4 = self._uptake_residual_no3[i], self._uptake_residual_nh4[i]
            assert self.state.no3[i] >= min(no3[i], r3) - _ULP
            assert self.state.nh4[i] >= min(nh4[i], r4) - _ULP
        calls.append(taken)
        return taken

    monkeypatch.setattr(NitrogenCycle, "_take_up_plant", checked)
    profile = _soil("loam_temperate")
    whole_profile_residual = sum(
        0.75 * ly.bulk_density_g_cm3 * ly.depth_cm / 10.0 for ly in profile.layers
    )
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", "netherlands_temperate"
    )
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "netherlands_temperate"
    ]
    orch = FullSimulationOrchestrator(
        profile, crop=crop, latitude_deg=climate.latitude_deg
    )
    season_minima: list[float] = []
    for year in (2024, 2025):
        if year == 2025:
            orch.reset_crop(crop)
        series = SyntheticWeatherGenerator(climate, seed=42).generate(
            150, date(year, 4, 15)
        )
        mineral_n: list[float] = []
        for rec in series.records:
            orch.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
            mineral_n.append(sum(orch.n_state.no3) + sum(orch.n_state.nh4))
        season_minima.append(min(mineral_n))
    assert sum(1 for taken in calls if taken > 0.0) > 100
    assert all(m > 0.5 * whole_profile_residual for m in season_minima), season_minima
