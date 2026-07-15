"""Unit + multi-cycle tests for the sulfur module (issue #212, non-redox)."""

from __future__ import annotations

from typing import Any, cast

import pytest

from agrogame.events import EventBus
from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.water.events import WaterDrained
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.nitrogen import NutrientLeached
from agrogame.soil.sulfur import (
    SoilSulfurState,
    SulfurAdsorbed,
    SulfurCycle,
    SulfurMineralized,
)


def make_profile(organic_matter_pct: float = 3.0) -> SoilProfile:
    layers = [
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.12,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=20,
            organic_matter_pct=organic_matter_pct,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
            initial_s_kg_ha=20.0,
        ),
        SoilLayer(
            depth_cm=30,
            texture="loam",
            field_capacity=0.28,
            wilting_point=0.11,
            saturation=0.42,
            bulk_density_g_cm3=1.35,
            ksat_mm_per_hour=18,
            organic_matter_pct=organic_matter_pct * 0.6,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
            initial_s_kg_ha=0.0,
        ),
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.27,
            wilting_point=0.10,
            saturation=0.40,
            bulk_density_g_cm3=1.4,
            ksat_mm_per_hour=15,
            organic_matter_pct=organic_matter_pct * 0.4,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
            initial_s_kg_ha=0.0,
        ),
    ]
    return SoilProfile(name="test", layers=layers)


def _cycle(
    profile: SoilProfile, bus: EventBus, *, with_water: bool = True
) -> tuple[SulfurCycle, SoilSulfurState]:
    state = SoilSulfurState(profile)
    water = SoilWaterState(profile) if with_water else None
    cycle = SulfurCycle(
        bus,
        state,
        water_state=cast(Any, water),
        profile=cast(Any, profile) if with_water else None,
    )
    return cycle, state


# --- Pools ------------------------------------------------------------------
def test_pools_initialized_by_layer() -> None:
    profile = make_profile()
    state = SoilSulfurState(profile)
    # Available SO4 seeded from initial_s_kg_ha; only top layer here.
    assert state.available_s == [20.0, 0.0, 0.0]
    # Adsorbed starts empty; organic S seeded from organic matter.
    assert state.adsorbed_s == [0.0, 0.0, 0.0]
    assert all(o > 0.0 for o in state.organic_s)
    assert state.total_sulfur_kg_ha() == pytest.approx(20.0 + sum(state.organic_s))


# --- Mineralization ---------------------------------------------------------
def test_mineralization_rate_1_to_3_percent_per_month_at_25c() -> None:
    """Validation plan: 1-3% of organic S mineralized per month at 25 °C."""
    profile = make_profile()
    bus = EventBus()
    # No water_state/profile -> moisture factor 1.0, isolating the rate law.
    cycle, state = _cycle(profile, bus, with_water=False)
    organic0 = sum(state.organic_s)

    events: list[SulfurMineralized] = []
    bus.subscribe(SulfurMineralized, events.append)

    mineralized = 0.0
    for _ in range(30):
        flux = cycle.daily_step(temperature_c=25.0, ph_by_layer=[7.0, 7.0, 7.0])
        mineralized += flux.mineralized_kg_ha

    frac = mineralized / organic0
    assert 0.01 <= frac <= 0.03
    assert events  # SulfurMineralized emitted


def test_temperature_increases_mineralization() -> None:
    profile = make_profile()
    bus = EventBus()
    cycle, _ = _cycle(profile, bus, with_water=False)
    cold = cycle.daily_step(temperature_c=10.0, ph_by_layer=[7.0, 7.0, 7.0])
    warm = cycle.daily_step(temperature_c=25.0, ph_by_layer=[7.0, 7.0, 7.0])
    assert warm.mineralized_kg_ha > cold.mineralized_kg_ha


# --- Adsorption -------------------------------------------------------------
def test_acidic_ph_increases_net_adsorption() -> None:
    profile = make_profile(organic_matter_pct=0.0)  # isolate adsorption
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    state.available_s = [20.0, 0.0, 0.0]

    adsorb_events: list[SulfurAdsorbed] = []
    bus.subscribe(SulfurAdsorbed, adsorb_events.append)

    acid = cycle.daily_step(temperature_c=20.0, ph_by_layer=[4.5, 7.0, 7.0])

    state.available_s = [20.0, 0.0, 0.0]
    state.adsorbed_s = [0.0, 0.0, 0.0]
    neutral = cycle.daily_step(temperature_c=20.0, ph_by_layer=[7.0, 7.0, 7.0])

    assert acid.adsorbed_kg_ha > neutral.adsorbed_kg_ha
    assert acid.adsorbed_kg_ha > 0.0
    assert adsorb_events


def test_adsorption_is_reversible_desorbs_from_loaded_pool() -> None:
    profile = make_profile(organic_matter_pct=0.0)
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    # Large adsorbed pool, no solution S: net movement is desorption (negative).
    state.available_s = [0.0, 0.0, 0.0]
    state.adsorbed_s = [50.0, 0.0, 0.0]
    flux = cycle.daily_step(temperature_c=20.0, ph_by_layer=[7.0, 7.0, 7.0])
    assert flux.adsorbed_kg_ha < 0.0
    assert state.available_s[0] > 0.0


# --- Uptake -----------------------------------------------------------------
def test_uptake_follows_root_fractions_and_reduces_available() -> None:
    profile = make_profile(organic_matter_pct=0.0)
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    state.available_s = [10.0, 10.0, 10.0]
    before = sum(state.available_s)
    flux = cycle.daily_step(
        temperature_c=20.0,
        plant_demand_kg_ha=6.0,
        root_fractions=[0.7, 0.2, 0.1],
        ph_by_layer=[7.0, 7.0, 7.0],
    )
    assert flux.plant_uptake_kg_ha == pytest.approx(6.0, abs=1e-6)
    # Most uptake comes from the top (highest root fraction) layer.
    assert state.available_s[0] < state.available_s[2]
    # Uptake is the only sink from the (available + adsorbed) solid/solution
    # S; the small adsorption transfer stays within those pools.
    solution_solid = sum(state.available_s) + sum(state.adsorbed_s)
    assert solution_solid == pytest.approx(before - 6.0, abs=1e-6)


def test_uptake_limited_by_availability_at_extreme_ph() -> None:
    profile = make_profile(organic_matter_pct=0.0)
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    state.available_s = [10.0, 0.0, 0.0]
    low = cycle.daily_step(
        temperature_c=20.0,
        plant_demand_kg_ha=8.0,
        root_fractions=[1.0, 0.0, 0.0],
        ph_by_layer=[3.5, 7.0, 7.0],
    )
    state2 = SoilSulfurState(profile)
    state2.available_s = [10.0, 0.0, 0.0]
    cycle2 = SulfurCycle(bus, state2)
    ok = cycle2.daily_step(
        temperature_c=20.0,
        plant_demand_kg_ha=8.0,
        root_fractions=[1.0, 0.0, 0.0],
        ph_by_layer=[7.0, 7.0, 7.0],
    )
    assert ok.plant_uptake_kg_ha >= low.plant_uptake_kg_ha


# --- Leaching (nitrate-like via WaterDrained) -------------------------------
def test_sulfate_leaches_out_of_profile_on_drainage() -> None:
    profile = make_profile()
    bus = EventBus()
    cycle, state = _cycle(profile, bus)

    leached: list[NutrientLeached] = []
    bus.subscribe(NutrientLeached, leached.append)

    storage0 = SoilWaterState(profile).layer_storage_mm(profile, 0)
    before = state.available_s[0]
    # Drain most of the layer's water out of the profile.
    bus.emit(WaterDrained(from_layer=0, to_layer=999, amount_mm=storage0 * 0.8))

    assert state.available_s[0] < before
    so4 = [e for e in leached if e.nutrient == "SO4"]
    assert so4 and so4[0].amount_kg_ha > 0.0


def test_sulfate_moves_between_layers_on_internal_drainage() -> None:
    profile = make_profile()
    bus = EventBus()
    cycle, state = _cycle(profile, bus)
    state.available_s = [20.0, 0.0, 0.0]
    storage0 = SoilWaterState(profile).layer_storage_mm(profile, 0)
    bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=storage0 * 0.5))
    assert state.available_s[0] < 20.0
    assert state.available_s[1] > 0.0


# --- Fertilizer -------------------------------------------------------------
def test_gypsum_increases_available_pool_immediately() -> None:
    profile = make_profile(organic_matter_pct=0.0)
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    before = state.available_s[0]
    cycle.apply_gypsum(layer=0, amount_kg_s_ha=50.0)
    assert state.available_s[0] == pytest.approx(before + 50.0)


def test_elemental_s_releases_full_amount_over_days() -> None:
    profile = make_profile(organic_matter_pct=0.0)
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    baseline = state.total_sulfur_kg_ha()
    cycle.apply_elemental_s(layer=0, amount_kg_s_ha=30.0, release_days=10)
    # Total conserved immediately (immediate + pending both counted).
    assert cycle._total_s() == pytest.approx(baseline + 30.0)
    for _ in range(10):
        cycle.daily_step(temperature_c=20.0, ph_by_layer=[7.0, 7.0, 7.0])
    assert cycle._total_s() == pytest.approx(baseline + 30.0)
    # No pending schedule remains.
    assert all(not s for s in cycle._slow_release_schedules)


# --- Mass balance -----------------------------------------------------------
def test_mass_balance_conserved_without_inputs_or_outputs() -> None:
    profile = make_profile()
    bus = EventBus()
    cycle, state = _cycle(profile, bus)
    before = state.total_sulfur_kg_ha()
    cycle.daily_step(temperature_c=20.0, ph_by_layer=[6.5, 6.5, 6.5])
    # Mineralization + adsorption are internal transfers; total is conserved.
    assert abs(state.total_sulfur_kg_ha() - before) < 1e-9


def test_mass_balance_across_two_cycles_with_inputs_and_outputs() -> None:
    """|S_start + inputs − S_end − uptake − leached| < 0.01 kg/ha (>=2 cycles)."""
    profile = make_profile()
    bus = EventBus()
    cycle, state = _cycle(profile, bus)

    leached: list[float] = []
    bus.subscribe(
        NutrientLeached,
        lambda e: leached.append(e.amount_kg_ha) if e.nutrient == "SO4" else None,
    )

    baseline = state.total_sulfur_kg_ha()
    inputs = 0.0
    uptake_total = 0.0
    storage0 = SoilWaterState(profile).layer_storage_mm(profile, 0)

    # Two 30-day cycles, each with a fertilizer pulse and drainage events.
    for _ in range(2):
        cycle.apply_gypsum(layer=0, amount_kg_s_ha=25.0)
        inputs += 25.0
        cycle.apply_elemental_s(layer=0, amount_kg_s_ha=15.0, release_days=20)
        inputs += 15.0
        for day in range(30):
            flux = cycle.daily_step(
                temperature_c=22.0,
                plant_demand_kg_ha=0.4,
                root_fractions=[0.7, 0.2, 0.1],
                ph_by_layer=[6.0, 6.5, 6.8],
            )
            uptake_total += flux.plant_uptake_kg_ha
            if day % 10 == 5:
                # Heavy drainage of the SO4-rich top layer out of the profile.
                bus.emit(
                    WaterDrained(from_layer=0, to_layer=999, amount_mm=storage0 * 0.6)
                )

    end = cycle._total_s()
    residual = baseline + inputs - end - uptake_total - sum(leached)
    assert sum(leached) > 0.0  # leaching actually happened
    assert uptake_total > 0.0  # uptake actually happened
    assert abs(residual) < 0.01


# --- Runtime + shared wiring ------------------------------------------------
def test_runtime_emits_sulfur_stress_on_nutrients_phase() -> None:
    from datetime import date

    from agrogame.events.calendar import DayTick
    from agrogame.plant.events import NutrientStressComputed
    from agrogame.soil.sulfur.runtime import SulfurRuntime

    profile = make_profile(organic_matter_pct=0.0)
    bus = EventBus()
    cycle, state = _cycle(profile, bus, with_water=False)
    state.available_s = [0.0, 0.0, 0.0]  # no S available -> full stress
    SulfurRuntime(bus, cycle)

    stresses: list[NutrientStressComputed] = []
    bus.subscribe(NutrientStressComputed, stresses.append)

    # Non-nutrients phase is ignored.
    bus.emit(DayTick(sim_date=date(2026, 6, 1), phase="water"))
    assert not stresses

    bus.emit(
        DayTick(
            sim_date=date(2026, 6, 1),
            phase="nutrients",
            plant_s_demand_kg_ha=5.0,
        )
    )
    s = [e for e in stresses if e.nutrient == "S"]
    assert s and s[0].stress == pytest.approx(0.0)


def test_daytick_carries_plant_s_demand() -> None:
    from datetime import date

    from agrogame.events.calendar import DayTick

    tick = DayTick(
        sim_date=date(2026, 6, 1), phase="nutrients", plant_s_demand_kg_ha=3.5
    )
    assert tick.plant_s_demand_kg_ha == 3.5
    # Defaults to None when unset (back-compatible with existing callers).
    default_tick = DayTick(sim_date=date(2026, 6, 1), phase="nutrients")
    assert default_tick.plant_s_demand_kg_ha is None


def test_stress_factors_and_combine_include_sulfur() -> None:
    from agrogame.plant.stress import StressCalculator, StressFactors

    sf = StressFactors()
    assert sf.sulfur == 1.0

    liebig = StressCalculator("liebig")
    # Sulfur is the most limiting factor -> Liebig min picks it.
    assert liebig.combine(1.0, 1.0, 1.0, sulfur=0.4) == pytest.approx(0.4)
    # Default sulfur=1.0 leaves 3-arg callers unchanged.
    assert liebig.combine(0.6, 0.8, 0.9) == pytest.approx(0.6)

    mult = StressCalculator("multiplicative")
    assert mult.combine(0.5, 0.5, 1.0, sulfur=0.5) == pytest.approx(0.125)
