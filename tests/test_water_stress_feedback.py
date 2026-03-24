from __future__ import annotations

from pathlib import Path

from agrogame.soil.canopy.params import CanopyParams


def test_stress_memory_dampens_recovery() -> None:
    """After drought, a single good day shouldn't fully restore growth."""
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date, timedelta

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    start = date(2024, 6, 1)

    # Scenario A: 20 dry days then 1 wet day (long enough to deplete soil)
    orch_a = FullSimulationOrchestrator(profile)
    for i in range(20):
        orch_a.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=20.0,
            tmax_c=30.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )
    biomass_after_drought = orch_a.canopy.state.biomass_g_m2
    orch_a.step_day(
        drivers=DailyDrivers(rainfall_mm=30.0),
        tmin_c=20.0,
        tmax_c=30.0,
        par_mj_m2=15.0,
        sim_date=start + timedelta(days=20),
    )
    recovery_inc = orch_a.canopy.state.biomass_g_m2 - biomass_after_drought

    # Scenario B: always wet (no stress history)
    orch_b = FullSimulationOrchestrator(profile)
    for i in range(20):
        orch_b.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=20.0,
            tmax_c=30.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )
    biomass_before = orch_b.canopy.state.biomass_g_m2
    orch_b.step_day(
        drivers=DailyDrivers(rainfall_mm=5.0),
        tmin_c=20.0,
        tmax_c=30.0,
        par_mj_m2=15.0,
        sim_date=start + timedelta(days=20),
    )
    normal_inc = orch_b.canopy.state.biomass_g_m2 - biomass_before

    # Recovery day after drought should produce less than a normal day
    assert recovery_inc < normal_inc


def test_vpd_reduces_growth_in_hot_dry() -> None:
    """High VPD (hot + dry) should reduce biomass more than same temp with water."""
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date, timedelta

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    start = date(2024, 7, 1)

    # Well-watered (low VPD effect)
    orch_wet = FullSimulationOrchestrator(profile)
    for i in range(30):
        orch_wet.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=20.0,
            tmax_c=30.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )

    # Dry (high VPD effect)
    orch_dry = FullSimulationOrchestrator(profile)
    for i in range(30):
        orch_dry.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=20.0,
            tmax_c=30.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )

    assert orch_dry.canopy.state.biomass_g_m2 < orch_wet.canopy.state.biomass_g_m2


def test_wilt_damage_reduces_lai() -> None:
    """Prolonged severe stress should permanently reduce LAI."""
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date, timedelta

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    start = date(2024, 7, 1)

    orch = FullSimulationOrchestrator(profile)
    # Build up some LAI with good conditions
    for i in range(30):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=20.0,
            tmax_c=30.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )
    lai_before_drought = orch.canopy.state.lai

    # Extended drought — should trigger wilt damage
    for i in range(30, 50):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=20.0,
            tmax_c=30.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )

    # LAI should have dropped due to wilt damage (not just senescence)
    assert orch.canopy.state.lai < lai_before_drought


def test_arid_produces_less_than_temperate() -> None:
    """Integration: arid climate should produce less biomass than temperate."""
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from agrogame.weather.presets import (
        load_climate_presets,
        _load_climate_presets_cached,
    )
    from agrogame.weather.generator import SyntheticWeatherGenerator
    from datetime import date

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    _load_climate_presets_cached.cache_clear()
    climates = load_climate_presets(Path("data/climate/presets.yaml"))

    # Netherlands: Apr-Sep
    nl = climates.climates["netherlands_temperate"]
    gen_nl = SyntheticWeatherGenerator(nl, seed=42)
    series_nl = gen_nl.generate(150, date(2024, 4, 1))
    orch_nl = FullSimulationOrchestrator(profile, latitude_deg=nl.latitude_deg)
    for rec in series_nl.records:
        orch_nl.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )

    # Sahel: Jun-Nov
    sahel = climates.climates["sahel_arid"]
    gen_sahel = SyntheticWeatherGenerator(sahel, seed=42)
    series_sahel = gen_sahel.generate(150, date(2024, 6, 1))
    orch_sahel = FullSimulationOrchestrator(profile, latitude_deg=sahel.latitude_deg)
    for rec in series_sahel.records:
        orch_sahel.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )

    # Sahel should produce less than Netherlands with water stress feedback
    assert orch_sahel.canopy.state.biomass_g_m2 < orch_nl.canopy.state.biomass_g_m2


def test_canopy_params_water_stress_defaults() -> None:
    p = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
    )
    assert p.vpd_rue_ref_kpa == 1.5
    assert p.wilt_days_for_damage == 5
    assert p.stress_memory_days == 7
