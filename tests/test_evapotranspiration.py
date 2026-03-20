from __future__ import annotations

from pathlib import Path

from agrogame.atmosphere.et import EtParams, Evapotranspiration
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
    actual = et.actual_et(profile, ws, water, comps, root_fractions=(1.0, 0.0, 0.0))
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


def test_vpd_reduces_potential_transpiration_in_partitioning() -> None:
    et = Evapotranspiration(EtParams())
    et0 = 6.0
    lai = 3.0
    vpd_low = vpd_kpa(20.0, 90.0)
    c_low = et.potential_components_with_vpd(et0_mm=et0, lai=lai, vpd_kpa=vpd_low)
    vpd_high = vpd_kpa(20.0, 20.0)
    c_high = et.potential_components_with_vpd(et0_mm=et0, lai=lai, vpd_kpa=vpd_high)
    assert c_high.potential_transp_mm <= c_low.potential_transp_mm
