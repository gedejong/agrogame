from __future__ import annotations

from pathlib import Path

from agrogame.soil.canopy.params import CanopyParams


def test_stress_memory_dampens_recovery() -> None:
    """After drought, a single good day shouldn't fully restore growth.

    Re-baselined for ADR-014 (Phase 3d): the ``crop=None`` orchestrator builds
    only a token default canopy, and under the corrected (halved) PAR basis it
    transpires so little that 20 dry days leave the soil essentially undepleted
    (Ta/Tp = 1.0) — no stress history accrues, so the recovery and normal
    increments were exactly equal and the assertion had nothing to bite on. The
    dry window is extended 20 -> 30 days, which now genuinely exhausts the soil
    (Ta/Tp ≈ 0.003) so the stress-memory window (7 d) still holds a low average
    on the recovery day. The assertion shape is unchanged. Measured:
    recovery_inc ≈ 0.12 g/m² vs normal_inc ≈ 0.84 g/m².
    """
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date, timedelta

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    start = date(2024, 6, 1)

    # Scenario A: 30 dry days then 1 wet day (long enough to deplete soil)
    orch_a = FullSimulationOrchestrator(profile)
    for i in range(30):
        orch_a.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=20.0,
            tmax_c=30.0,
            shortwave_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )
    biomass_after_drought = orch_a.canopy.state.biomass_g_m2
    orch_a.step_day(
        drivers=DailyDrivers(rainfall_mm=30.0),
        tmin_c=20.0,
        tmax_c=30.0,
        shortwave_mj_m2=15.0,
        sim_date=start + timedelta(days=30),
    )
    recovery_inc = orch_a.canopy.state.biomass_g_m2 - biomass_after_drought

    # Scenario B: always wet (no stress history)
    orch_b = FullSimulationOrchestrator(profile)
    for i in range(30):
        orch_b.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=20.0,
            tmax_c=30.0,
            shortwave_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )
    biomass_before = orch_b.canopy.state.biomass_g_m2
    orch_b.step_day(
        drivers=DailyDrivers(rainfall_mm=5.0),
        tmin_c=20.0,
        tmax_c=30.0,
        shortwave_mj_m2=15.0,
        sim_date=start + timedelta(days=30),
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
            shortwave_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )

    # Dry (high VPD effect)
    orch_dry = FullSimulationOrchestrator(profile)
    for i in range(30):
        orch_dry.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=20.0,
            tmax_c=30.0,
            shortwave_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )

    assert orch_dry.canopy.state.biomass_g_m2 < orch_wet.canopy.state.biomass_g_m2


def test_wilt_damage_reduces_lai() -> None:
    """Prolonged severe stress should permanently reduce LAI.

    Re-baselined for ADR-014 (Phase 3d). Under the corrected (halved) PAR basis
    the canopy transpires less and undisturbed deep roots buffer the drought, so
    Ta/Tp stays above the wilt onset for far longer: a 30-day-canopy + 20-day
    drought now sees LAI *climb* (only ~7 sub-onset days, swamped by growth), and
    even a longer drought on a young canopy reduces LAI mostly by phenological
    aging, not wilt. Real drought senescence fires only once the soil is
    genuinely exhausted to Ta/Tp ≈ 0.05, which on this loam takes ~50 days of a
    large canopy drawing it down. The establishment (30 -> 45 d, LAI ~3.33) and
    drought (20 -> 60 d) are extended so the collapse is genuine wilt damage:
    LAI falls 3.33 -> ~1.12 with ~0.79 LAI of DroughtSenescenceApplied, and the
    drought canopy ends well below a watered control run for the same days
    (~2.07), confirming the drop is drought-driven, not phenology.
    """
    from agrogame.plant.presets import load_crop_presets
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date, timedelta

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    start = date(2024, 7, 1)

    # Use a real maize crop with adequate N so the crop establishes a genuine
    # canopy that drought can then knock down. Under the stock-based critical-N
    # model (#360), the bare ``crop=None`` orchestrator requests only a token
    # 0.1 kg N/ha/day and never builds a stock, so its canopy stays tiny
    # (LAI ~0.6), transpires little, and drought never bites — which invalidates
    # this test's large-canopy premise. Supplying a real crop + fertiliser
    # isolates *water-stress wilt damage* from N-limitation, mirroring the
    # adaptation already made to ``test_demand_trajectory_rise_then_decline``.
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(profile, crop=crops.crops["maize"])
    orch.apply_fertilizer("ammonium_nitrate", 200.0)
    # Build up a solid canopy with good conditions (45 d -> LAI ~3.33).
    for i in range(45):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=20.0,
            tmax_c=30.0,
            shortwave_mj_m2=15.0,
            sim_date=start + timedelta(days=i),
        )
    lai_before_drought = orch.canopy.state.lai

    # Extended drought — long enough to exhaust the soil and trigger real wilt
    # senescence (not just phenological decline).
    for i in range(45, 105):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=20.0,
            tmax_c=30.0,
            shortwave_mj_m2=15.0,
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
            shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )

    # Sahel drought: extreme water limitation should clearly produce less
    sahel = climates.climates["sahel_arid"]
    gen_sahel = SyntheticWeatherGenerator(sahel, seed=42)
    series_sahel = gen_sahel.generate(150, date(2024, 6, 1), "drought")
    orch_sahel = FullSimulationOrchestrator(profile, latitude_deg=sahel.latitude_deg)
    for rec in series_sahel.records:
        orch_sahel.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )

    # Sahel drought should produce less than Netherlands normal
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
