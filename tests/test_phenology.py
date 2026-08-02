from __future__ import annotations

import warnings

import pytest

from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
    PhenologyStage,
)


def _params() -> CropPhenologyParams:
    return CropPhenologyParams(
        base_temperature_c=10.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )


def test_gdd_accumulation_and_stage_changes() -> None:
    params = CropPhenologyParams(
        base_temperature_c=10.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )
    pheno = PhenologyModule(params)

    # 20 days at (tmin=8, tmax=22) -> mean=16 -> gdd/day = 6 -> 120 gdd
    for _ in range(20):
        state = pheno.daily_step(tmin_c=8.0, tmax_c=22.0)

    assert state.accumulated_gdd >= 120.0
    # Should have reached at least emerged/vegetative
    assert state.stage in (PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE)

    # Run until flowering
    while state.accumulated_gdd < params.thresholds.flowering_gdd:
        state = pheno.daily_step(tmin_c=12.0, tmax_c=28.0)

    assert state.stage in (PhenologyStage.FLOWERING, PhenologyStage.GRAIN_FILL)


def test_update_daily_shim_warns_and_matches_daily_step() -> None:
    """Deprecated ``update_daily`` shim warns and yields identical state (#282)."""
    canonical = PhenologyModule(_params())
    shimmed = PhenologyModule(_params())

    new_state = canonical.daily_step(tmin_c=12.0, tmax_c=28.0, photoperiod_h=14.0)
    with pytest.warns(DeprecationWarning, match="daily_step"):
        old_state = shimmed.update_daily(tmin_c=12.0, tmax_c=28.0, photoperiod_h=14.0)

    assert old_state == new_state


def test_update_daily_shim_stacklevel_points_at_caller() -> None:
    """stacklevel=2 makes the warning reference the caller's file (#282)."""
    pheno = PhenologyModule(_params())
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pheno.update_daily(tmin_c=12.0, tmax_c=28.0)

    assert len(caught) == 1
    assert issubclass(caught[0].category, DeprecationWarning)
    assert caught[0].filename == __file__
