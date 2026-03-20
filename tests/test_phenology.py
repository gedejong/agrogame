from __future__ import annotations

from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
    PhenologyStage,
)


def test_gdd_accumulation_and_stage_changes():
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
        state = pheno.update_daily(tmin_c=8.0, tmax_c=22.0)

    assert state.accumulated_gdd >= 120.0
    # Should have reached at least emerged/vegetative
    assert state.stage in (PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE)

    # Run until flowering
    while state.accumulated_gdd < params.thresholds.flowering_gdd:
        state = pheno.update_daily(tmin_c=12.0, tmax_c=28.0)

    assert state.stage in (PhenologyStage.FLOWERING, PhenologyStage.GRAIN_FILL)
