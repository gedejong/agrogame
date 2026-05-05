from __future__ import annotations

import argparse
import csv
from pathlib import Path

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather
from agrogame.sim.builder import SimulationBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple weather-driven scenario")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--weather-file", type=Path, required=True)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("out/summary.csv"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]
    app = SimulationBuilder().build(profile)
    et = Evapotranspiration(EtParams())

    weather = load_weather(args.weather_file)

    rows: list[list[str | float]] = [["day", "et0", "act_evap", "act_transp", "lai"]]
    for i in range(min(args.days, len(weather.records))):
        rec = weather.records[i]
        rain = rec.precip_mm or 0.0
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
        comps = et.potential_components(et0_mm=et0, lai=0.0)
        # Drive one day via calendar
        app.calendar.tick(
            sim_date=rec.day,
            drivers=DailyDrivers(
                rainfall_mm=rain,
                evaporation_mm=0.0,
                irrigation_mm=0.0,
            ),
            target_ph=6.8,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
        )

        # Actual ET diagnostics via module (optional)
        # Minimal ET diagnostic call is omitted; values below are demand-based
        class _Actual:
            evaporation_mm = 0.0
            transpiration_mm = comps.potential_transp_mm

        actual = _Actual()
        rows.append(
            [
                rec.day.isoformat(),
                et0,
                actual.evaporation_mm,
                actual.transpiration_mm,
                0.0,
            ]
        )

    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
