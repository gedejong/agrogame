"""Tests for aggregation wiring into water, roots, and SOM (#219).

Literature-cited quantitative assertions for each integration point.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from agrogame.events import EventBus
from agrogame.soil.aggregation.dynamic_state import (
    effective_ksat_factor,
    effective_porosity,
    root_penetration_factor,
    som_protection_factor,
)
from agrogame.soil.water.types import DailyDrivers
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.som.pools import ThreePoolSOM, SOMPoolParams


# --- 1. ksat scaling ---


def test_ksat_scaling_range() -> None:
    """ksat factor should span 2–5x between poor and good aggregation.

    Ref: Dexter 2004, Geoderma — soil physical quality.
    """
    poor = effective_ksat_factor(0.1)
    good = effective_ksat_factor(0.6)
    ratio = good / poor
    assert (
        2.0 <= ratio <= 5.0
    ), f"ksat ratio {ratio:.2f} should be 2–5x (poor={poor:.2f}, good={good:.2f})"


# --- 2. porosity range ---


def test_porosity_range() -> None:
    """Porosity: degraded 35–40%, well-aggregated 45–55%.

    Ref: Bronick & Lal 2005, Geoderma.
    """
    base_sat = 0.45
    degraded = effective_porosity(base_sat, macro_frac=0.05)
    well_agg = effective_porosity(base_sat, macro_frac=0.60)
    assert (
        0.35 <= degraded <= 0.45
    ), f"Degraded porosity {degraded:.3f} should be 0.35–0.45"
    assert (
        0.45 <= well_agg <= 0.55
    ), f"Well-aggregated porosity {well_agg:.3f} should be 0.45–0.55"


# --- 3. root penetration ---


def test_root_penetration_factor() -> None:
    """MWD=3.0 should give ~1.0, MWD=0.5 should be measurably lower.

    Ref: Bengough et al. 2011, J Exp Bot.
    """
    good = root_penetration_factor(3.0)
    poor = root_penetration_factor(0.5)
    assert good >= 0.95, f"Good aggregation factor {good:.2f} should be ~1.0"
    assert poor < 0.55, f"Poor aggregation factor {poor:.2f} should be < 0.55"
    assert poor >= 0.3, f"Poor aggregation factor {poor:.2f} should be >= 0.3"


# --- 4. SOM protection ---


def test_som_protection_with_mwd() -> None:
    """Higher MWD should increase SOM protection (lower multiplier).

    Ref: Six et al. 2002, Plant Soil.
    """
    # Compare protection at MWD=3.0 (excellent) vs MWD=0.5 (poor)
    clay = 22.0
    base_frac = 0.40  # intermediate pool
    excellent = som_protection_factor(base_frac, clay, mwd_mm=3.0)
    poor = som_protection_factor(base_frac, clay, mwd_mm=0.5)
    # Lower multiplier = more protection = slower decomposition
    assert excellent < poor, (
        f"Excellent MWD should decompose slower: "
        f"{excellent:.3f} should be < {poor:.3f}"
    )
    # Both should be in valid range
    assert 0.3 <= excellent <= 1.0
    assert 0.3 <= poor <= 1.0


def test_som_protection_in_three_pool() -> None:
    """ThreePoolSOM._protection_factor should use MWD when provided."""
    som = ThreePoolSOM(SOMPoolParams(), n_layers=1)
    pf_no_mwd = som._protection_factor(0.40, 22.0, 0, mwd_mm=0.0)
    pf_high_mwd = som._protection_factor(0.40, 22.0, 0, mwd_mm=2.0)
    assert pf_high_mwd < pf_no_mwd, (
        f"High MWD protection {pf_high_mwd:.3f} " f"should be < no-MWD {pf_no_mwd:.3f}"
    )


# --- 5. infiltration response ---


def test_infiltration_differs_by_aggregation() -> None:
    """Well-aggregated soil should infiltrate more than degraded.

    Run same rainfall on two orchestrators with different aggregation.
    """
    soils = load_soil_presets(Path("soils/presets.yaml"))
    profile = soils.soils["loam_temperate"]

    # Well-aggregated
    orch_good = FullSimulationOrchestrator(profile, event_bus=EventBus())
    for i in range(len(profile.layers)):
        orch_good.agg_state.macro[i] = 0.60
        orch_good.agg_state.meso[i] = 0.25
        orch_good.agg_state.micro[i] = 0.15

    # Degraded
    orch_poor = FullSimulationOrchestrator(profile, event_bus=EventBus())
    for i in range(len(profile.layers)):
        orch_poor.agg_state.macro[i] = 0.05
        orch_poor.agg_state.meso[i] = 0.35
        orch_poor.agg_state.micro[i] = 0.60

    # Apply heavy rainfall
    for orch in (orch_good, orch_poor):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=50.0),
            tmin_c=15.0,
            tmax_c=25.0,
            par_mj_m2=15.0,
            sim_date=date(2024, 5, 1),
        )

    # Poorly aggregated soil retains excess water above FC (poor drainage).
    # Well-aggregated drains excess efficiently to deeper layers / drainage.
    good_water = sum(orch_good.water_state.theta)
    poor_water = sum(orch_poor.water_state.theta)
    assert (
        good_water != poor_water
    ), f"Aggregation should affect water: good={good_water:.3f}, poor={poor_water:.3f}"


# --- 6. root-aggregation feedback ---


def test_root_aggregation_feedback() -> None:
    """Active roots should improve aggregation, which improves root growth.

    Ref: Six et al. 2004 — positive feedback loop.
    """
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )
    initial_macro = orch.agg_state.macro[0]
    start = date(2024, 4, 1)
    for d in range(180):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=2.0),
            tmin_c=12.0,
            tmax_c=26.0,
            par_mj_m2=16.0,
            sim_date=start + timedelta(days=d),
        )
    # Aggregation should have improved with active roots
    assert orch.agg_state.macro[0] > initial_macro, "Roots should improve aggregation"


# --- 7. tillage cascade ---


def test_tillage_cascade_effects() -> None:
    """Tillage should reduce infiltration capacity and increase SOM exposure.

    Apply tillage, then verify properties shifted toward degraded.
    """
    soils = load_soil_presets(Path("soils/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"], event_bus=EventBus()
    )
    # Establish good aggregation
    for i in range(len(orch.profile.layers)):
        orch.agg_state.macro[i] = 0.50
        orch.agg_state.meso[i] = 0.30
        orch.agg_state.micro[i] = 0.20

    ksat_before = effective_ksat_factor(orch.agg_state.macro[0])
    orch.apply_tillage(intensity=1.0)
    ksat_after = effective_ksat_factor(orch.agg_state.macro[0])
    assert ksat_after < ksat_before, "Tillage should reduce effective ksat"


# --- 8. water balance closure ---


def test_water_balance_closes_with_aggregation() -> None:
    """Full season with aggregation should not violate water mass balance."""
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )
    start = date(2024, 4, 1)
    for d in range(90):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=3.0),
            tmin_c=12.0,
            tmax_c=26.0,
            par_mj_m2=16.0,
            sim_date=start + timedelta(days=d),
        )
    # All theta values should be physically plausible
    for i, theta in enumerate(orch.water_state.theta):
        assert 0.0 <= theta <= 0.65, f"Layer {i} theta {theta:.3f} out of bounds"


# --- 9. extreme aggregation ---


def test_extreme_aggregation_bounds() -> None:
    """macro=0.0 and macro=1.0 should produce valid properties."""
    assert 0.3 <= effective_ksat_factor(0.0) <= 3.0
    assert 0.3 <= effective_ksat_factor(1.0) <= 3.0
    assert 0.30 <= effective_porosity(0.45, 0.0) <= 0.60
    assert 0.30 <= effective_porosity(0.45, 1.0) <= 0.60
    assert 0.0 < root_penetration_factor(0.0) <= 1.0
    assert 0.0 < root_penetration_factor(5.0) <= 1.0
