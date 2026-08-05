"""ADR-014 radiation-convention guards.

The day-tick radiation field is raw incoming shortwave Rs, and every physical
reduction is applied *inside* its consumer: the canopy derives intercepted PAR
as ``PAR_FRACTION·Rs·(1 − e^{−k·LAI})``; ET derives ``Rn = NET_RAD_FRACTION·Rs``.
No entry point may pre-apply a fraction at the boundary.

These tests are deliberately general: the cross-path parity check would have
caught all four ``× 0.48`` double-application sites reconciled in #414/#418 (and
would catch a future 5th), because it asserts that the *same raw Rs* produces the
*same biomass* regardless of entry point — a pre-applied fraction on any path
surfaces as a mismatch.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from agrogame.weather.constants import PAR_FRACTION


def test_canopy_interception_applies_par_fraction_to_raw_shortwave() -> None:
    """``calculate_light_interception(Rs)`` returns ``PAR_FRACTION·Rs·f_int``.

    The argument is raw shortwave Rs; the canopy applies ``PAR_FRACTION`` itself
    before Beer-Lambert interception (Monteith 1977; FAO-56). This pins the exact
    physical form a caller must not duplicate by pre-scaling Rs.
    """
    from agrogame.events import EventBus
    from agrogame.soil.canopy.module import CanopyModule, CanopyParams

    k = 0.6
    lai = 3.0
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=k,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=EventBus(),
    )
    canopy.state.lai = lai
    for rs in (10.0, 18.0, 25.0, 32.0):
        fx = canopy.calculate_light_interception(rs)
        expected = PAR_FRACTION * rs * (1.0 - math.exp(-k * lai))
        assert fx.intercepted_par_mj_m2 == pytest.approx(expected)
        # Intercepted PAR is a fraction of incident PAR, itself < Rs.
        assert fx.intercepted_par_mj_m2 < PAR_FRACTION * rs <= rs


def test_cross_path_biomass_parity_for_equal_shortwave() -> None:
    """Equal raw Rs → equal biomass via the dashboard path and the orchestrator.

    The dashboard entry point routes Rs through ``compute_reference_et`` →
    ``par`` → ``step_day``. If that (or any) entry point pre-applied ``f_PAR``,
    the dashboard would feed ``0.48·Rs`` into a canopy that reapplies ``f_PAR``,
    halving biomass relative to the orchestrator fed raw Rs. Parity therefore
    fails the instant any caller pre-scales the boundary field.
    """
    from agrogame.api.dashboard_facade import (
        DashboardSimulationRun,
        WeatherRecord,
        load_soil_profile,
        make_drivers,
    )
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers

    rs = 22.0  # raw incoming shortwave Rs (MJ m-2 d-1)
    tmin_c, tmax_c = 12.0, 26.0
    n_days = 8

    # --- Dashboard path: Rs enters as rec.shortwave_mj_m2 ---
    run = DashboardSimulationRun(load_soil_profile())
    run.orch.canopy.state.lai = 3.0
    rec = WeatherRecord(
        day=date(2026, 6, 1),
        tmin_c=tmin_c,
        tmax_c=tmax_c,
        relative_humidity_pct=60.0,
        wind_m_s=2.0,
        shortwave_mj_m2=rs,
        net_radiation_mj_m2=None,
        albedo=0.23,
        precip_mm=0.0,
    )
    for _ in range(n_days):
        _et0, _pt, par, _rn, _tmean, _vpd = run.compute_reference_et(rec)
        # The boundary field must be raw Rs — no f_PAR pre-applied here.
        assert par == pytest.approx(rs)
        run.step_day(
            make_drivers(0.0), tmin_c=tmin_c, tmax_c=tmax_c, shortwave_mj_m2=par
        )
    dashboard_biomass = run.biomass_g_m2

    # --- Orchestrator path: same raw Rs fed directly ---
    orch = FullSimulationOrchestrator(load_soil_profile())
    orch.canopy.state.lai = 3.0
    for _ in range(n_days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=tmin_c,
            tmax_c=tmax_c,
            shortwave_mj_m2=rs,
        )
    orchestrator_biomass = orch.canopy.state.biomass_g_m2

    assert dashboard_biomass > 0.0
    assert dashboard_biomass == pytest.approx(orchestrator_biomass, rel=1e-9)


def test_step_day_par_mj_m2_kwarg_is_deprecated_alias() -> None:
    """The legacy ``par_mj_m2=`` kwarg delegates to ``shortwave_mj_m2`` (#436).

    ADR-014 renamed the day-tick radiation field; the old name is kept as a
    deprecated alias (compatibility shim, per the ``daily_step`` #282/#411
    discipline) so external callers migrate incrementally. It must warn and stay
    byte-identical to the canonical kwarg on the simple orchestrator boundary.
    """
    import warnings

    from agrogame.sim.orchestrator import build_default_orchestrator

    new = build_default_orchestrator()
    old = build_default_orchestrator()
    for _ in range(15):
        new.step_day(tmin_c=10.0, tmax_c=26.0, shortwave_mj_m2=12.0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(15):
            old.step_day(tmin_c=10.0, tmax_c=26.0, par_mj_m2=12.0)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert old.canopy.state.biomass_g_m2 == pytest.approx(new.canopy.state.biomass_g_m2)
    assert old.canopy.state.lai == pytest.approx(new.canopy.state.lai)


def test_full_orchestrator_par_mj_m2_alias_matches_shortwave() -> None:
    """Same deprecated-alias parity on the ``FullSimulationOrchestrator`` boundary."""
    import warnings

    from agrogame.api.dashboard_facade import load_soil_profile
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers

    sim_date = date(2024, 4, 1)
    new = FullSimulationOrchestrator(load_soil_profile())
    old = FullSimulationOrchestrator(load_soil_profile())
    for _ in range(20):
        new.step_day(
            drivers=DailyDrivers(rainfall_mm=1.0),
            tmin_c=9.0,
            tmax_c=22.0,
            shortwave_mj_m2=15.0,
            sim_date=sim_date,
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for _ in range(20):
            old.step_day(
                drivers=DailyDrivers(rainfall_mm=1.0),
                tmin_c=9.0,
                tmax_c=22.0,
                par_mj_m2=15.0,
                sim_date=sim_date,
            )
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert old.canopy.state.biomass_g_m2 == pytest.approx(new.canopy.state.biomass_g_m2)


def test_step_day_rejects_both_and_missing_radiation_kwargs() -> None:
    """Passing both radiation names, or neither, is a ``TypeError`` (no ambiguity)."""
    from agrogame.sim.orchestrator import build_default_orchestrator

    orch = build_default_orchestrator()
    with pytest.raises(TypeError):
        orch.step_day(tmin_c=10.0, tmax_c=26.0, shortwave_mj_m2=12.0, par_mj_m2=12.0)
    with pytest.raises(TypeError):
        orch.step_day(tmin_c=10.0, tmax_c=26.0)
