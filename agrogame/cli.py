from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agrogame.soil.loader import load_soil_presets
from .sim.builder import SimulationBuilder
from .sim.engine import SimulationEngine


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgroGame CLI")
    sub = parser.add_subparsers(dest="cmd", required=False)

    run_p = sub.add_parser("run", help="Run simple scenario via builder")
    run_p.add_argument("--profile", default="loam_temperate")
    run_p.add_argument("--weather-file", type=Path, required=True)
    run_p.add_argument("--days", type=int, default=60)

    eng_p = sub.add_parser("engine", help="Run season using SimulationEngine")
    eng_p.add_argument("--profile", default="loam_temperate")
    eng_p.add_argument("--weather-file", type=Path, required=True)
    eng_p.add_argument("--speed", type=int, default=1, choices=[1, 10, 100])
    eng_p.add_argument("--irrigate", nargs=2, metavar=("DAY", "MM"), action="append")
    eng_p.add_argument(
        "--fert-an", nargs=3, metavar=("DAY", "KG_HA", "LAYER"), action="append"
    )
    return parser


def _handle_run(profile_name: str, weather_file: Path, days: int) -> int:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    app = SimulationBuilder().build(profile)
    from agrogame.weather import load_weather
    from agrogame.soil.water.types import DailyDrivers

    weather = load_weather(weather_file)
    for i in range(min(days, len(weather.records))):
        rec = weather.records[i]
        rain = rec.precip_mm or 0.0
        par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
        app.calendar.tick(
            sim_date=rec.day,
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            target_ph=6.8,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
        )
    print("Scenario run completed")
    return 0


def _handle_engine(
    profile_name: str,
    weather_file: Path,
    speed: int,
    irrigate: list | None,
    fert_an: list | None,
) -> int:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    eng = SimulationEngine(profile, str(weather_file))
    eng.set_speed(speed)
    for day, mm in irrigate or []:
        eng.schedule_irrigation(int(day), float(mm))
    for day, kg, layer in fert_an or []:
        eng.schedule_fertilizer_an(int(day), float(kg), int(layer))
    res = eng.run_season()
    print(
        "Days processed: ",
        res.days_processed,
        ", finished: ",
        res.finished,
        ", time(s): ",
        f"{res.total_runtime_s:.3f}",
    )
    return 0


def main() -> int:
    parser = _build_parser()

    # If invoked in environments that pass unrelated args (e.g., pytest),
    # short-circuit to the stub unless a known subcommand is present.
    argv_rest = sys.argv[1:]
    if not any(tok in {"run", "engine"} for tok in argv_rest):
        print("AgroGame simulation CLI stub. Use 'poetry run simulate' to run.")
        return 0

    args, _unknown = parser.parse_known_args()

    if not getattr(args, "cmd", None):
        print("AgroGame simulation CLI stub. Use 'poetry run simulate' to run.")
        return 0

    if args.cmd == "run":
        return _handle_run(args.profile, args.weather_file, args.days)
    if args.cmd == "engine":
        return _handle_engine(
            args.profile, args.weather_file, args.speed, args.irrigate, args.fert_an
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
