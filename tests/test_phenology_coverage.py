"""Tests covering missing lines in phenology/module.py and phenology/factory.py."""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
    PhenologyStage,
)
from agrogame.soil.phenology.factory import build_from_crop_params
from agrogame.params.models import CropParameters, ThermalTime, Roots, Biomass


# ---------------------------------------------------------------------------
# PhenologyModule — photoperiod sensitivity (lines 37-40)
# ---------------------------------------------------------------------------


def test_photoperiod_sensitivity() -> None:
    """Cover lines 37-40: photoperiod adjusts GDD."""
    params = CropPhenologyParams(
        base_temperature_c=10.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=800.0, maturity_gdd=1500.0
        ),
        photoperiod_sensitivity=0.5,
    )
    pheno = PhenologyModule(params)
    # Long day (14h) should increase GDD
    state = pheno.update_daily(tmin_c=15.0, tmax_c=25.0, photoperiod_h=14.0)
    gdd_long = state.accumulated_gdd

    pheno2 = PhenologyModule(params)
    state2 = pheno2.update_daily(tmin_c=15.0, tmax_c=25.0, photoperiod_h=10.0)
    gdd_short = state2.accumulated_gdd

    assert gdd_long > gdd_short


# ---------------------------------------------------------------------------
# PhenologyModule — vernalization gating (lines 53-57)
# ---------------------------------------------------------------------------


def test_vernalization_accumulation() -> None:
    """Cover lines 53-57: vernalization units accumulate in cool range."""
    params = CropPhenologyParams(
        base_temperature_c=0.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=50.0, flowering_gdd=300.0, maturity_gdd=600.0
        ),
        vernalization_required_units=30,
    )
    pheno = PhenologyModule(params)
    # Cool temps accumulate vernal units
    for _ in range(40):
        state = pheno.update_daily(tmin_c=2.0, tmax_c=8.0)
    assert state.vernalization_units >= 30.0


def test_vernalization_blocks_flowering() -> None:
    """Cover lines 84-87: vernalization gates flowering."""
    params = CropPhenologyParams(
        base_temperature_c=0.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=10.0, flowering_gdd=100.0, maturity_gdd=300.0
        ),
        vernalization_required_units=1000,  # very high requirement
    )
    pheno = PhenologyModule(params)
    # Warm temps: lots of GDD but no vernalization
    for _ in range(50):
        state = pheno.update_daily(tmin_c=20.0, tmax_c=30.0)
    # Should be vegetative but not flowering due to vernalization requirement
    assert state.accumulated_gdd > 100.0
    assert state.stage in (
        PhenologyStage.EMERGED,
        PhenologyStage.VEGETATIVE,
    )


# ---------------------------------------------------------------------------
# Full cycle through maturity (lines 94, 99)
# ---------------------------------------------------------------------------


def test_full_cycle_to_maturity() -> None:
    """Cover lines 94 (GRAIN_FILL) and 99 (MATURITY)."""
    params = CropPhenologyParams(
        base_temperature_c=10.0,
        max_temperature_c=40.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=50.0, flowering_gdd=200.0, maturity_gdd=400.0
        ),
    )
    bus = EventBus()
    pheno = PhenologyModule(params, event_bus=bus)
    for _ in range(200):
        state = pheno.update_daily(tmin_c=15.0, tmax_c=30.0)
        if state.stage == PhenologyStage.MATURITY:
            break
    assert state.stage == PhenologyStage.MATURITY


# ---------------------------------------------------------------------------
# Factory: build_from_crop_params (lines 13-28)
# ---------------------------------------------------------------------------


def test_build_from_crop_params() -> None:
    """Cover all lines in phenology/factory.py."""
    crop = CropParameters(
        name="test_wheat",
        thermal_time=ThermalTime(
            base_temp_c=0.0,
            emergence_dd=100.0,
            flowering_dd=800.0,
            maturity_dd=1500.0,
        ),
        roots=Roots(
            max_depth_cm=100.0,
            growth_rate_cm_per_day=1.0,
            distribution=[0.4, 0.3, 0.3],
        ),
        biomass=Biomass(
            rue_g_per_mj=3.0,
            harvest_index=0.45,
            partition_vegetative={"leaf": 0.4, "stem": 0.4, "root": 0.2},
            partition_reproductive={
                "leaf": 0.1,
                "stem": 0.1,
                "root": 0.05,
                "grain": 0.75,
            },
        ),
    )
    pheno = build_from_crop_params(crop)
    assert pheno.params.base_temperature_c == 0.0
    assert pheno.params.max_temperature_c == 45.0  # default
    assert pheno.params.thresholds.emergence_gdd == 100.0
