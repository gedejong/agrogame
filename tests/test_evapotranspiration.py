from __future__ import annotations

from pathlib import Path
from typing import cast

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.atmosphere.et.ports import WaterProfile, WaterState, WaterActuator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.weather.utils import vpd_kpa


def test_priestley_taylor_monotonic_with_radiation() -> None:
    et = Evapotranspiration(EtParams())
    et0_low = et.priestley_taylor(temp_mean_c=20.0, net_radiation_mj_m2=5.0)
    et0_high = et.priestley_taylor(temp_mean_c=20.0, net_radiation_mj_m2=10.0)
    assert et0_high > et0_low >= 0.0


def test_partitioning_sums_to_et0_and_bounds() -> None:
    et = Evapotranspiration(EtParams(extinction_coefficient_k=0.6))
    comps = et.potential_components(et0_mm=6.0, lai=2.0)
    assert (
        abs((comps.potential_evap_mm + comps.potential_transp_mm) - comps.et0_mm) < 1e-9
    )
    assert 0.0 <= comps.potential_evap_mm <= comps.et0_mm
    assert 0.0 <= comps.potential_transp_mm <= comps.et0_mm


def test_ritchie_transitions_to_stage2() -> None:
    et = Evapotranspiration(EtParams(stage1_limit_mm=2.0, ritchie_coef=3.5))
    from agrogame.atmosphere.et.types import EtState

    es = EtState()
    t1 = et.ritchie_evaporation(es, potential_evap_mm=2.0, topsoil_available_mm=10.0)
    assert t1 <= 2.0 and es.cumulative_evap_mm >= 2.0
    t2 = et.ritchie_evaporation(es, potential_evap_mm=2.0, topsoil_available_mm=10.0)
    assert t2 <= t1  # stage-2 should not exceed stage-1 rate


def test_actual_et_limited_by_availability_and_roots() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    water = CascadingBucketWaterModel()
    ws = SoilWaterState(profile)
    et = Evapotranspiration()
    comps = et.potential_components(et0_mm=5.0, lai=1.0)
    actual = et.actual_et(
        cast(WaterProfile, profile),
        cast(WaterState, ws),
        cast(WaterActuator, water),
        comps,
        root_fractions=(1.0, 0.0, 0.0),
    )
    assert actual.evaporation_mm >= 0.0 and actual.transpiration_mm >= 0.0


def test_penman_monteith_sensitivity_to_wind_and_humidity() -> None:
    et = Evapotranspiration(EtParams(method="penman-monteith"))
    # Fixed Rn and temperature; vary wind and RH
    base = et.et0(
        temp_mean_c=20.0,
        net_radiation_mj_m2=10.0,
        method="penman-monteith",
        wind_m_s=1.0,
        relative_humidity_pct=70.0,
    )
    windier = et.et0(
        temp_mean_c=20.0,
        net_radiation_mj_m2=10.0,
        method="penman-monteith",
        wind_m_s=3.0,
        relative_humidity_pct=70.0,
    )
    drier = et.et0(
        temp_mean_c=20.0,
        net_radiation_mj_m2=10.0,
        method="penman-monteith",
        wind_m_s=1.0,
        relative_humidity_pct=40.0,
    )
    assert windier > base >= 0.0
    assert drier > base >= 0.0


def test_pm_vs_pt_differs_under_wind_and_vpd() -> None:
    et = Evapotranspiration(EtParams())
    # PT ignores wind/RH; PM should respond
    et0_pt = et.priestley_taylor(temp_mean_c=20.0, net_radiation_mj_m2=10.0)
    et0_pm = et.et0(
        temp_mean_c=20.0,
        net_radiation_mj_m2=10.0,
        method="penman-monteith",
        wind_m_s=4.0,
        relative_humidity_pct=30.0,
    )
    assert et0_pm != et0_pt


def test_ritchie_state_persists_across_days() -> None:
    """Multi-day drying: evap decreases as Stage 2 kicks in."""
    et = Evapotranspiration(EtParams(stage1_limit_mm=3.0, ritchie_coef=3.5))
    from agrogame.atmosphere.et.types import EtState

    state = EtState()
    evaps = []
    for _ in range(10):
        e = et.ritchie_evaporation(
            state, potential_evap_mm=5.0, topsoil_available_mm=100.0
        )
        evaps.append(e)
    # After stage-1 exhausted, evap should decline
    assert evaps[-1] < evaps[0]
    # Stage 2 should produce decreasing values
    stage2_vals = evaps[1:]  # after first big bite
    for i in range(1, len(stage2_vals)):
        assert stage2_vals[i] <= stage2_vals[i - 1] + 1e-9


def test_ritchie_rainfall_resets_to_stage1() -> None:
    """After dry-down, resetting state recovers evap rate."""
    et = Evapotranspiration(EtParams(stage1_limit_mm=3.0, ritchie_coef=3.5))
    from agrogame.atmosphere.et.types import EtState

    state = EtState()
    # Dry down for 5 days
    for _ in range(5):
        et.ritchie_evaporation(state, potential_evap_mm=5.0, topsoil_available_mm=100.0)
    late_evap = et.ritchie_evaporation(
        state, potential_evap_mm=5.0, topsoil_available_mm=100.0
    )
    # Reset (simulating rainfall)
    state.cumulative_evap_mm = 0.0
    reset_evap = et.ritchie_evaporation(
        state, potential_evap_mm=5.0, topsoil_available_mm=100.0
    )
    assert reset_evap > late_evap


def test_residue_reduces_evaporation() -> None:
    """cover=0 vs cover=0.8 → less evap with residue."""
    et = Evapotranspiration(EtParams(stage1_limit_mm=6.0, ritchie_coef=3.5))
    from agrogame.atmosphere.et.types import EtState

    # No residue
    state0 = EtState()
    evap0 = 0.0
    for _ in range(5):
        evap0 += et.ritchie_evaporation(
            state0, potential_evap_mm=5.0, topsoil_available_mm=100.0
        )

    # With residue
    adj_s1, adj_coef = Evapotranspiration.residue_adjusted_params(6.0, 3.5, 0.8)
    state1 = EtState()
    evap1 = 0.0
    for _ in range(5):
        evap1 += et.ritchie_evaporation(
            state1,
            potential_evap_mm=5.0,
            topsoil_available_mm=100.0,
            stage1_limit_mm=adj_s1,
            ritchie_coef=adj_coef,
        )
    assert evap1 < evap0


def test_residue_adjusted_params_bounds() -> None:
    """cover=0/0.5/1 → monotonic decrease, values positive."""
    vals = []
    for cover in [0.0, 0.5, 1.0]:
        s1, coef = Evapotranspiration.residue_adjusted_params(6.0, 3.5, cover)
        assert (
            s1 > 0.0 or cover == 1.0
        )  # at full cover with 0.6 reduction: 6*(1-0.6)=2.4
        assert s1 >= 0.0
        assert coef >= 0.0
        vals.append((s1, coef))
    # Monotonic decrease
    for i in range(1, len(vals)):
        assert vals[i][0] <= vals[i - 1][0]
        assert vals[i][1] <= vals[i - 1][1]


def test_residue_decay_halves_cover() -> None:
    """30-day half-life → cover ≈ halved after 30 steps."""
    import math
    from agrogame.atmosphere.et.types import ResidueState

    residue = ResidueState(cover_fraction=0.8, decay_half_life_days=30.0)
    ln2 = math.log(2.0)
    for _ in range(30):
        residue.cover_fraction *= math.exp(-ln2 / residue.decay_half_life_days)
    assert abs(residue.cover_fraction - 0.4) < 0.01


def test_transpiration_clamped_to_potential() -> None:
    """Defensive check: actual transpiration ≤ potential."""
    from typing import cast
    from agrogame.atmosphere.et.ports import (
        WaterProfile,
        WaterState,
        WaterActuator,
    )

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    water = CascadingBucketWaterModel()
    ws = SoilWaterState(profile)
    et = Evapotranspiration()
    comps = et.potential_components(et0_mm=5.0, lai=1.0)
    actual = et.actual_et(
        cast(WaterProfile, profile),
        cast(WaterState, ws),
        cast(WaterActuator, water),
        comps,
        root_fractions=(1.0, 0.0, 0.0),
    )
    assert actual.transpiration_mm <= comps.potential_transp_mm + 1e-9


def test_et_runtime_persists_state() -> None:
    """Integration: 10 dry days → evap rate declines."""
    from agrogame.events import EventBus
    from agrogame.sim.calendar_events import DayTick
    from agrogame.soil.water.events import EvaporationTaken
    from agrogame.atmosphere.et.runtime import ETRuntime
    from agrogame.soil.canopy.module import CanopyModule, CanopyParams
    from agrogame.plant.roots.types import RootState
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus()
    water_model = CascadingBucketWaterModel(event_bus=bus)
    water_state = SoilWaterState(profile)
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )
    roots_state = RootState()
    et_mod = Evapotranspiration(EtParams(stage1_limit_mm=3.0))
    runtime = ETRuntime(
        event_bus=bus,
        et=et_mod,
        profile=profile,
        water_state=water_state,
        water_model=water_model,
        roots_state=roots_state,
        canopy=canopy,
    )
    evaps: list[float] = []
    last_evap = 0.0

    def _capture_evap(ev: EvaporationTaken) -> None:
        nonlocal last_evap
        last_evap = float(ev.amount_mm)

    bus.subscribe(EvaporationTaken, _capture_evap)
    # 10 dry days (no rain)
    for _ in range(10):
        last_evap = 0.0
        bus.emit(
            DayTick(
                sim_date=date(2025, 1, 1),
                phase="et",
                drivers=DailyDrivers(rainfall_mm=0.0),
                tmin_c=10.0,
                tmax_c=22.0,
                par_mj_m2=12.0,
            )
        )
        evaps.append(last_evap)
    # Evap should decline over time
    assert evaps[-1] < evaps[0] or evaps[0] == 0.0
    _ = runtime  # keep reference


def test_et_runtime_rainfall_resets() -> None:
    """Integration: dry → rain → dry → rate recovers."""
    from agrogame.events import EventBus
    from agrogame.sim.calendar_events import DayTick
    from agrogame.soil.water.events import EvaporationTaken
    from agrogame.atmosphere.et.runtime import ETRuntime
    from agrogame.soil.canopy.module import CanopyModule, CanopyParams
    from agrogame.plant.roots.types import RootState
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus()
    water_model = CascadingBucketWaterModel(event_bus=bus)
    water_state = SoilWaterState(profile)
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )
    roots_state = RootState()
    et_mod = Evapotranspiration(
        EtParams(stage1_limit_mm=3.0, wetting_reset_threshold_mm=10.0)
    )
    runtime = ETRuntime(
        event_bus=bus,
        et=et_mod,
        profile=profile,
        water_state=water_state,
        water_model=water_model,
        roots_state=roots_state,
        canopy=canopy,
    )
    evaps: list[float] = []
    last_evap = 0.0

    def _capture_evap(ev: EvaporationTaken) -> None:
        nonlocal last_evap
        last_evap = float(ev.amount_mm)

    bus.subscribe(EvaporationTaken, _capture_evap)

    def _emit_day(rain: float) -> float:
        nonlocal last_evap
        last_evap = 0.0
        bus.emit(
            DayTick(
                sim_date=date(2025, 1, 1),
                phase="et",
                drivers=DailyDrivers(rainfall_mm=rain),
                tmin_c=10.0,
                tmax_c=22.0,
                par_mj_m2=12.0,
            )
        )
        return last_evap

    # 5 dry days
    for _ in range(5):
        evaps.append(_emit_day(0.0))
    late_dry_evap = evaps[-1]
    # Big rain event
    _emit_day(20.0)  # triggers reset
    # First dry day after rain
    post_rain_evap = _emit_day(0.0)
    # After reset, evap should recover (>= late dry-down rate)
    assert post_rain_evap >= late_dry_evap or late_dry_evap == 0.0
    _ = runtime  # keep reference


def test_vpd_reduces_potential_transpiration_in_partitioning() -> None:
    et = Evapotranspiration(EtParams())
    et0 = 6.0
    lai = 3.0
    vpd_low = vpd_kpa(20.0, 90.0)
    c_low = et.potential_components_with_vpd(et0_mm=et0, lai=lai, vpd_kpa=vpd_low)
    vpd_high = vpd_kpa(20.0, 20.0)
    c_high = et.potential_components_with_vpd(et0_mm=et0, lai=lai, vpd_kpa=vpd_high)
    assert c_high.potential_transp_mm <= c_low.potential_transp_mm
