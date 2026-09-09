from __future__ import annotations

from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
    PhenologyStage,
    PhenologyState,
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


def test_development_stage_tracks_thermal_time() -> None:
    params = _params()
    pheno = PhenologyModule(params)
    assert pheno.development_stage() == 0.0

    previous = 0.0
    state = pheno.state
    while state.stage != PhenologyStage.MATURITY:
        state = pheno.daily_step(tmin_c=14.0, tmax_c=30.0)
        dvs = pheno.development_stage()
        assert dvs >= previous, "DVS never runs backwards"
        if state.stage in (PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE):
            assert 0.0 < dvs < 1.0
        elif state.stage in (PhenologyStage.FLOWERING, PhenologyStage.GRAIN_FILL):
            assert 1.0 <= dvs < 2.0
        previous = dvs
    assert pheno.development_stage() == 2.0

    # Mid grain fill sits mid-way between the flowering and maturity thresholds.
    pheno = PhenologyModule(params)
    pheno.state = PhenologyState(
        accumulated_gdd=1300.0, stage=PhenologyStage.GRAIN_FILL
    )
    assert pheno.development_stage() == 1.5


def test_development_stage_caps_before_anthesis_when_vernalization_unmet() -> None:
    params = CropPhenologyParams(
        base_temperature_c=10.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
        vernalization_required_units=30.0,
    )
    pheno = PhenologyModule(params)
    # Warm days accumulate thermal time but never vernalization.
    for _ in range(200):
        state = pheno.daily_step(tmin_c=18.0, tmax_c=30.0)
    assert state.stage == PhenologyStage.VEGETATIVE
    assert state.accumulated_gdd > params.thresholds.flowering_gdd
    assert pheno.development_stage() == 0.99
