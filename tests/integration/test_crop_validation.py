from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, Any

import os
import csv
import pytest

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.atmosphere.et.types import EtComponents
from agrogame.weather import load_weather
from agrogame.analysis.stats import r2, nse


pytestmark = [
    pytest.mark.bench,
    pytest.mark.skipif(
        os.getenv("AGRO_BENCH") != "1",
        reason="Integration benchmarks gated; set AGRO_BENCH=1 to run",
    ),
]


def _scenario_cfg() -> Dict[str, Any]:
    import yaml

    return yaml.safe_load(Path("tests/data/benchmarks/scenarios.yaml").read_text())


SCENARIOS: Dict[str, Path] = {
    "maize_iowa": Path("tests/data/benchmarks/fullseason/maize_iowa.csv"),
    "wheat_kansas": Path("tests/data/benchmarks/fullseason/wheat_kansas.csv"),
    "maize_kenya_drought": Path(
        "tests/data/benchmarks/fullseason/maize_kenya_drought.csv"
    ),
}


def _yield_t_ha_from_biomass_g_m2(biomass_g_m2: float, harvest_index: float) -> float:
    return harvest_index * biomass_g_m2 * 0.01


def _run_one(name: str, weather_file: Path) -> Dict[str, float | int | None]:
    import yaml

    cfg = yaml.safe_load(Path("tests/data/benchmarks/scenarios.yaml").read_text())
    sc = cfg[name]
    rue = float(sc.get("rue_g_per_mj", 3.0))
    hi = float(sc.get("harvest_index", 0.5))
    lai0 = float(sc.get("planting_lai", 0.0))
    soil_id = str(sc.get("soil_id", "loam_temperate"))
    vernal_units = sc.get("vernalization_required_units")

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils.get(soil_id, lib.soils["loam_temperate"])
    bus = EventBus()
    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
            vernalization_required_units=(
                float(vernal_units) if vernal_units is not None else None
            ),
        ),
        event_bus=bus,
    )
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=rue,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )
    et = Evapotranspiration(EtParams())
    water = CascadingBucketWaterModel()
    wstate = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)
    weather = load_weather(weather_file)
    canopy.state.lai = lai0

    flowering_gdd = None
    maturity_gdd = None
    total_et_mm = 0.0
    total_n_uptake = 0.0
    biomass_series: Dict[int, float] = {}

    for i, rec in enumerate(weather.records):
        st = phen.update_daily(tmin_c=rec.tmin_c, tmax_c=rec.tmax_c, photoperiod_h=12.0)
        if flowering_gdd is None and st.stage.name.lower() == "flowering":
            flowering_gdd = st.accumulated_gdd
        if maturity_gdd is None and st.stage.name.lower() == "maturity":
            maturity_gdd = st.accumulated_gdd

        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
        et0 = et.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        rain = rec.precip_mm or 0.0
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=rain, evaporation_mm=0.0)
        )
        comps: EtComponents = et.potential_components(et0_mm=et0, lai=canopy.state.lai)
        actual = et.actual_et(
            profile,
            wstate,
            water,
            comps,
            root_fractions=tuple(
                [1.0 / max(1, len(profile.layers))] * len(profile.layers)
            ),
        )
        total_et_mm += actual.evaporation_mm + actual.transpiration_mm

        # Nitrogen dynamics (simplified: track pool decrease as uptake proxy)
        no3_before = sum(nstate.no3)
        _ = ncycle.daily_step(temperature_c=tmean, plant_demand_kg_ha=1.0)
        no3_after = sum(nstate.no3)
        total_n_uptake += max(0.0, no3_before - no3_after)

        _ = canopy.daily_step_with_transpiration(
            incident_par_mj_m2=par,
            temp_factor=1.0,
            actual_transpiration_mm=actual.transpiration_mm,
            potential_transpiration_mm=comps.potential_transp_mm,
            n_stress=1.0,
        )
        biomass_series[i] = canopy.state.biomass_g_m2

    final_biomass = canopy.state.biomass_g_m2
    return {
        "yield_t_ha": _yield_t_ha_from_biomass_g_m2(final_biomass, hi),
        "wue": final_biomass / max(1e-6, total_et_mm),
        "flowering_gdd": flowering_gdd,
        "maturity_gdd": maturity_gdd,
        "total_n_uptake": total_n_uptake,
        "biomass_series_len": len(biomass_series),
        # Provide series metrics by comparing to observed if available
        "r2_obs": _compare_biomass_series_r2(biomass_series),
        "nse_obs": _compare_biomass_series_nse(biomass_series),
    }


def _read_observed_series() -> Dict[int, float] | None:
    path = Path("tests/data/observed_biomass.csv")
    if not path.exists():
        return None
    out: Dict[int, float] = {}
    with path.open("r", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        for row in rd:
            day = int(row.get("day", "0"))
            val = float(row.get("biomass_g_m2", "0"))
            out[day] = val
    return out


def _align_on_days(
    sim: Dict[int, float], obs: Dict[int, float]
) -> Tuple[list[float], list[float]]:
    keys = sorted(set(sim.keys()) & set(obs.keys()))
    return [obs[k] for k in keys], [sim[k] for k in keys]


def _compare_biomass_series_r2(sim: Dict[int, float]) -> float | None:
    obs = _read_observed_series()
    if not obs:
        return None
    y_obs, y_sim = _align_on_days(sim, obs)
    if not y_obs or not y_sim:
        return None
    return float(r2(y_obs, y_sim))


def _compare_biomass_series_nse(sim: Dict[int, float]) -> float | None:
    obs = _read_observed_series()
    if not obs:
        return None
    y_obs, y_sim = _align_on_days(sim, obs)
    if not y_obs or not y_sim:
        return None
    return float(nse(y_obs, y_sim))


@pytest.mark.parametrize("name", ["maize_iowa", "wheat_kansas", "maize_kenya_drought"])
def test_end_to_end_benchmarks(name: str) -> None:
    wf = SCENARIOS[name]
    if not wf.exists():
        pytest.skip(f"Missing benchmark weather: {wf}")
    cfg = _scenario_cfg()[name]
    res = _run_one(name, wf)
    # Yield within scenario absolute tolerance
    exp = float(cfg.get("expected_yield_t_ha", 0.0))
    tol = float(cfg.get("yield_tol_t_ha", 0.0))
    assert abs(float(res["yield_t_ha"]) - exp) <= tol
    # Phenology windows
    fgdd = float(res["flowering_gdd"]) if res["flowering_gdd"] is not None else None
    mgdd = float(res["maturity_gdd"]) if res["maturity_gdd"] is not None else None
    phen = cfg.get("phenology", {})
    fmin = phen.get("flowering_gdd_min")
    fmax = phen.get("flowering_gdd_max")
    mmin = phen.get("maturity_gdd_min")
    if fgdd is not None and fmin is not None:
        assert fgdd >= float(fmin)
    if fgdd is not None and fmax is not None:
        assert fgdd <= float(fmax)
    if mgdd is not None and mmin is not None:
        assert mgdd >= float(mmin)
    # WUE bounds
    wue_cfg = cfg.get("wue", {})
    wmin = float(wue_cfg.get("min", 0.0))
    wmax = float(wue_cfg.get("max", 1e9))
    assert wmin <= float(res["wue"]) <= wmax
    # N uptake bounds (kg/ha total)
    n_cfg = cfg.get("n_uptake_kg_ha", {})
    nmin = float(n_cfg.get("min", 0.0))
    nmax = float(n_cfg.get("max", 1e9))
    assert nmin <= float(res["total_n_uptake"]) <= nmax
    # Biomass series metrics if observed available
    metrics_cfg = cfg.get("series_metrics", {})
    r2_min = metrics_cfg.get("r2_min")
    nse_min = metrics_cfg.get("nse_min")
    if res["r2_obs"] is not None and r2_min is not None:
        assert float(res["r2_obs"]) >= float(r2_min)
    if res["nse_obs"] is not None and nse_min is not None:
        assert float(res["nse_obs"]) >= float(nse_min)
