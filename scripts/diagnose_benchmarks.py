from __future__ import annotations

from pathlib import Path

from agrogame.soil.loader import load_soil_presets
from agrogame.events import EventBus
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.atmosphere.et.types import EtComponents
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather


def _yield_t_ha_from_biomass_g_m2(
    biomass_g_m2: float, harvest_index: float = 0.5
) -> float:
    return harvest_index * biomass_g_m2 * 0.01


def diagnose(
    weather_file: Path,
    name: str,
    rue: float | None = None,
    hi: float | None = None,
    planting_lai: float | None = None,
    soil_id: str | None = None,
) -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    sid = soil_id or "loam_temperate"
    profile = lib.soils.get(sid) or lib.soils["loam_temperate"]
    bus = EventBus()
    # Basic defaults; allow scenario overrides for wheat vernalization
    phen_params = CropPhenologyParams(
        base_temperature_c=8.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )
    phen = PhenologyModule(phen_params, event_bus=bus)
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=(rue if rue is not None else 3.0),
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )
    et = Evapotranspiration(EtParams())
    water = CascadingBucketWaterModel()
    wstate = SoilWaterState(profile)
    weather = load_weather(weather_file)

    canopy.state.lai = planting_lai if planting_lai is not None else 0.0
    total_et_mm = 0.0
    flowering_idx = None
    maturity_idx = None
    flowering_gdd = None
    maturity_gdd = None

    for i, rec in enumerate(weather.records):
        state = phen.update_daily(
            tmin_c=rec.tmin_c, tmax_c=rec.tmax_c, photoperiod_h=12.0
        )
        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        et0 = et.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=0.0, evaporation_mm=0.0)
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
        _ = canopy.daily_step_with_transpiration(
            incident_par_mj_m2=rn,
            temp_factor=1.0,
            actual_transpiration_mm=actual.transpiration_mm,
            potential_transpiration_mm=comps.potential_transp_mm,
            n_stress=1.0,
        )
        if flowering_idx is None and state.stage.name.lower() == "flowering":
            flowering_idx = i
            flowering_gdd = state.accumulated_gdd
        if maturity_idx is None and state.stage.name.lower() == "maturity":
            maturity_idx = i
            maturity_gdd = state.accumulated_gdd

    final_biomass = canopy.state.biomass_g_m2
    y = _yield_t_ha_from_biomass_g_m2(
        final_biomass, harvest_index=(hi if hi is not None else 0.5)
    )
    wue = final_biomass / max(1e-6, total_et_mm)
    print(f"Scenario: {name}")
    print(f"  Weather: {weather_file}")
    hi_used = hi if hi is not None else 0.5
    print(f"  Final biomass: {final_biomass:.1f} g/m2")
    print(f"  Yield~ {y:.2f} t/ha (HI={hi_used})")
    print(f"  Total ET: {total_et_mm:.1f} mm, WUE: {wue:.2f} g/m2/mm")
    print(f"  Flowering idx/GDD: {flowering_idx} / {flowering_gdd}")
    print(f"  Maturity idx/GDD: {maturity_idx} / {maturity_gdd}")


def main() -> int:
    import yaml

    sc_path = Path("tests/data/benchmarks/scenarios.yaml")
    cfg = yaml.safe_load(sc_path.read_text())
    for name, sc in cfg.items():
        wf = Path(f"tests/data/benchmarks/fullseason/{name}.csv")
        if wf.exists():
            # Optional: per-scenario phenology tuning (e.g., vernalization for wheat)
            rue = float(sc.get("rue_g_per_mj", 3.0))
            hi = float(sc.get("harvest_index", 0.5))
            lai0 = float(sc.get("planting_lai", 0.0))
            soil_id = str(sc.get("soil_id", "loam_temperate"))
            diagnose(
                wf,
                name,
                rue=rue,
                hi=hi,
                planting_lai=lai0,
                soil_id=soil_id,
            )
        else:
            print(f"Scenario {name}: missing {wf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
