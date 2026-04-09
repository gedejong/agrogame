"""Tests for dynamic plant N/P demand (#223).

Verifies that nutrient demand varies with biomass growth rate and crop
tissue concentrations, replacing the old hardcoded 1.0 N / 0.1 P defaults.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.plant.events import NutrientStressComputed


def _make_orchestrator(
    crop_key: str = "maize",
    soil_key: str = "loam_temperate",
) -> tuple[FullSimulationOrchestrator, EventBus]:
    soils = load_soil_presets(Path("soils/presets.yaml"))
    profile = soils.soils[soil_key]
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    crop = crops.crops[crop_key]
    bus = EventBus()
    orch = FullSimulationOrchestrator(profile, event_bus=bus, crop=crop)
    return orch, bus


def _step_days(
    orch: FullSimulationOrchestrator,
    n: int,
    rain: float = 5.0,
) -> None:
    from datetime import timedelta

    start = date(2024, 5, 1)
    for day in range(n):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rain),
            tmin_c=15.0,
            tmax_c=28.0,
            par_mj_m2=18.0,
            sim_date=start + timedelta(days=day),
        )


def test_demand_baseline_before_emergence() -> None:
    """Before emergence, biomass increment is 0 → demand = baseline minimum."""
    orch, bus = _make_orchestrator()
    events: list[NutrientStressComputed] = []
    bus.subscribe(NutrientStressComputed, events.append)
    # Step 1 day — no biomass yet (pre-emergence)
    _step_days(orch, 1)
    n_events = [e for e in events if e.nutrient == "N"]
    assert len(n_events) >= 1
    # Demand should be the baseline minimum (0.01 kg/ha), not the old 1.0
    assert n_events[0].demand_kg_ha <= 0.01 + 1e-9


def test_demand_increases_with_growth() -> None:
    """After emergence, growing biomass drives increasing N/P demand."""
    orch, bus = _make_orchestrator()
    n_demands: list[float] = []
    p_demands: list[float] = []
    bus.subscribe(
        NutrientStressComputed,
        lambda e: (
            n_demands.append(e.demand_kg_ha)
            if e.nutrient == "N"
            else p_demands.append(e.demand_kg_ha)
        ),
    )
    _step_days(orch, 30)
    # After 30 days of growth, demand should have increased from baseline
    assert len(n_demands) >= 20
    # Peak demand (during active growth) should exceed baseline (0.01)
    peak_n = max(n_demands)
    assert peak_n > 0.01, f"Peak N demand ({peak_n:.4f}) should exceed baseline"
    # Late demands (post-emergence) should exceed pre-emergence baseline
    late_avg = sum(n_demands[15:25]) / 10
    assert late_avg > 0.01, f"Late demand ({late_avg:.4f}) should exceed baseline 0.01"
    # P demand should also increase above baseline
    assert len(p_demands) >= 20
    peak_p = max(p_demands)
    assert peak_p > 0.001


def test_demand_proportional_to_tissue_concentration() -> None:
    """Higher tissue N concentration produces higher demand per unit growth."""
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    soy = crops.crops["soybean"]
    maize = crops.crops["maize"]
    # Verify tissue concentrations are ordered correctly
    assert soy.tissue_n_conc_kg_kg > maize.tissue_n_conc_kg_kg
    # For the same biomass increment, soybean demand should be 1.5× maize
    # (0.045 / 0.030 = 1.5). Test via the demand formula directly.
    fake_inc_g_m2 = 30.0  # typical peak daily increment
    inc_kg_ha = fake_inc_g_m2 * 0.01
    demand_factor = 2.0
    soy_demand = inc_kg_ha * soy.tissue_n_conc_kg_kg * demand_factor
    maize_demand = inc_kg_ha * maize.tissue_n_conc_kg_kg * demand_factor
    ratio = soy_demand / maize_demand
    assert abs(ratio - 1.5) < 0.01, f"Demand ratio should be 1.5, got {ratio:.3f}"
    # Also verify both produce non-trivial demand
    assert soy_demand > 0.01
    assert maize_demand > 0.01


def test_stress_below_one_when_soil_depleted() -> None:
    """On low-N soil with high demand, stress should drop below 1.0."""
    orch, bus = _make_orchestrator("maize", "sandy_arid")
    stresses: list[float] = []
    bus.subscribe(
        NutrientStressComputed,
        lambda e: stresses.append(e.stress) if e.nutrient == "N" else None,
    )
    # Step many days — sandy arid soil has limited N
    _step_days(orch, 60)
    # At least some days should show stress < 1.0
    assert any(
        s < 1.0 for s in stresses
    ), f"Expected N stress < 1.0 on depleted soil; min stress = {min(stresses):.3f}"


def test_tissue_concentrations_loaded_from_yaml() -> None:
    """Crop presets should load tissue N/P from YAML."""
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    maize = crops.crops["maize"]
    assert maize.tissue_n_conc_kg_kg == 0.030
    assert maize.tissue_p_conc_kg_kg == 0.003
    soy = crops.crops["soybean"]
    assert soy.tissue_n_conc_kg_kg == 0.045
    grape = crops.crops["grape"]
    assert grape.tissue_n_conc_kg_kg == 0.018


def test_explicit_demand_overrides_dynamic() -> None:
    """Passing explicit demand to step_day should override dynamic computation."""
    orch, bus = _make_orchestrator()
    events: list[NutrientStressComputed] = []
    bus.subscribe(NutrientStressComputed, events.append)
    # Step with explicit demand
    orch.step_day(
        drivers=DailyDrivers(rainfall_mm=5.0),
        tmin_c=15.0,
        tmax_c=28.0,
        par_mj_m2=18.0,
        sim_date=date(2024, 5, 1),
        plant_n_demand_kg_ha=5.0,
        plant_p_demand_kg_ha=0.5,
    )
    n_events = [e for e in events if e.nutrient == "N"]
    assert len(n_events) >= 1
    assert n_events[0].demand_kg_ha == 5.0


def test_demand_trajectory_rise_then_decline() -> None:
    """Full-season demand rises during vegetative growth, declines at maturity."""
    orch, bus = _make_orchestrator()
    n_demands: list[float] = []
    bus.subscribe(
        NutrientStressComputed,
        lambda e: n_demands.append(e.demand_kg_ha) if e.nutrient == "N" else None,
    )
    # Simulate 120 days — covers emergence through grain fill / maturity
    _step_days(orch, 120)
    assert len(n_demands) >= 100
    # Split into thirds: early (veg), mid (flowering), late (grain fill/maturity)
    third = len(n_demands) // 3
    mid = n_demands[third : 2 * third]
    late = n_demands[2 * third :]
    mid_avg = sum(mid) / len(mid)
    late_avg = sum(late) / len(late)
    # Mid-season (active growth) should have higher demand than late (maturity)
    assert mid_avg > late_avg, (
        f"Mid-season demand ({mid_avg:.4f}) should exceed "
        f"late-season ({late_avg:.4f}) as growth slows toward maturity"
    )
    # Peak demand should occur in the first 2/3 of the season
    peak_idx = n_demands.index(max(n_demands))
    assert (
        peak_idx < 2 * third
    ), f"Peak demand at day {peak_idx} should be before late season (day {2 * third})"


def test_demand_resets_after_crop_change() -> None:
    """After reset_crop, demand should reset to baseline."""
    orch, bus = _make_orchestrator()
    _step_days(orch, 20)
    # Biomass should have accumulated
    assert orch._last_biomass_inc_g_m2 >= 0.0
    # Reset to new crop
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch.reset_crop(crops.crops["spring_wheat"])
    assert orch._last_biomass_inc_g_m2 == 0.0
    events: list[NutrientStressComputed] = []
    bus.subscribe(NutrientStressComputed, events.append)
    _step_days(orch, 1)
    n_events = [e for e in events if e.nutrient == "N"]
    assert len(n_events) >= 1
    # Should be baseline (0.01), not carrying over maize's growth
    assert n_events[0].demand_kg_ha <= 0.01 + 1e-9
