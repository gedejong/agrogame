from __future__ import annotations


from agrogame.soil.canopy.params import cardinal_temp_factor, CanopyParams


def test_below_base_returns_zero() -> None:
    assert cardinal_temp_factor(5.0, base=8.0, opt=30.0, tmax=42.0) == 0.0


def test_at_base_returns_zero() -> None:
    assert cardinal_temp_factor(8.0, base=8.0, opt=30.0, tmax=42.0) == 0.0


def test_at_optimum_returns_one() -> None:
    assert cardinal_temp_factor(30.0, base=8.0, opt=30.0, tmax=42.0) == 1.0


def test_above_max_returns_zero() -> None:
    assert cardinal_temp_factor(45.0, base=8.0, opt=30.0, tmax=42.0) == 0.0


def test_at_max_returns_zero() -> None:
    assert cardinal_temp_factor(42.0, base=8.0, opt=30.0, tmax=42.0) == 0.0


def test_midpoint_below_opt() -> None:
    # Halfway between base (8) and opt (30): x=0.5, sqrt(0.5) ≈ 0.707
    tf = cardinal_temp_factor(19.0, base=8.0, opt=30.0, tmax=42.0)
    assert abs(tf - 0.707) < 0.01


def test_midpoint_above_opt() -> None:
    # Halfway between opt (30) and max (42) → 0.5
    tf = cardinal_temp_factor(36.0, base=8.0, opt=30.0, tmax=42.0)
    assert abs(tf - 0.5) < 0.01


def test_maize_at_20c_in_target_range() -> None:
    # AC: maize at 20°C (base=8, opt=30) should give factor 0.6-0.8
    tf = cardinal_temp_factor(20.0, base=8.0, opt=30.0, tmax=42.0)
    assert 0.6 <= tf <= 0.8


def test_warm_reduces_below_one() -> None:
    tf = cardinal_temp_factor(38.0, base=8.0, opt=30.0, tmax=42.0)
    assert 0.0 < tf < 1.0


def test_cool_reduces_below_one() -> None:
    tf = cardinal_temp_factor(12.0, base=8.0, opt=30.0, tmax=42.0)
    assert 0.0 < tf < 1.0


def test_monotonic_below_opt() -> None:
    vals = [cardinal_temp_factor(t, 8.0, 30.0, 42.0) for t in range(8, 31)]
    for i in range(1, len(vals)):
        assert vals[i] >= vals[i - 1]


def test_monotonic_above_opt() -> None:
    vals = [cardinal_temp_factor(t, 8.0, 30.0, 42.0) for t in range(30, 43)]
    for i in range(1, len(vals)):
        assert vals[i] <= vals[i - 1]


def test_canopy_params_defaults() -> None:
    p = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
    )
    assert p.temp_base_c == 8.0
    assert p.temp_opt_c == 30.0
    assert p.temp_max_c == 42.0


def test_integration_heat_reduces_biomass() -> None:
    """Full integration: hot climate produces less biomass than optimal."""
    from pathlib import Path
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]

    # Run 30 days at optimal temperature (tmean=30°C)
    orch_opt = FullSimulationOrchestrator(profile)
    for _ in range(30):
        orch_opt.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=25.0,
            tmax_c=35.0,
            par_mj_m2=15.0,
        )
    biomass_opt = orch_opt.canopy.state.biomass_g_m2

    # Run 30 days at extreme heat (tmean=44°C, above temp_max=42)
    orch_hot = FullSimulationOrchestrator(profile)
    for _ in range(30):
        orch_hot.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=40.0,
            tmax_c=48.0,
            par_mj_m2=15.0,
        )
    biomass_hot = orch_hot.canopy.state.biomass_g_m2

    assert biomass_hot < biomass_opt


def test_integration_cold_reduces_biomass() -> None:
    """Full integration: cold climate produces less biomass than optimal."""
    from pathlib import Path
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]

    # Optimal
    orch_opt = FullSimulationOrchestrator(profile)
    for _ in range(30):
        orch_opt.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=25.0,
            tmax_c=35.0,
            par_mj_m2=15.0,
        )

    # Cold (tmean=6°C, below base=8)
    orch_cold = FullSimulationOrchestrator(profile)
    for _ in range(30):
        orch_cold.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=2.0,
            tmax_c=10.0,
            par_mj_m2=15.0,
        )

    assert orch_cold.canopy.state.biomass_g_m2 < orch_opt.canopy.state.biomass_g_m2
