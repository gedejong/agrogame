from __future__ import annotations

from argparse import ArgumentParser
from datetime import date as _date, timedelta as _td
from datetime import datetime as _dt
from pathlib import Path
from typing import Any

from agrogame.weather import load_weather, load_weather_auto
from agrogame.weather.types import WeatherSeries


def add_weather_args(parser: ArgumentParser) -> None:
    parser.add_argument("--weather-file", type=Path, help="CSV/JSON weather file")
    parser.add_argument(
        "--power-lat",
        type=float,
        default=53.22,
        help="NASA POWER latitude (default Groningen)",
    )
    parser.add_argument(
        "--power-lon",
        type=float,
        default=6.57,
        help="NASA POWER longitude (default Groningen)",
    )
    parser.add_argument("--power-start", type=str, help="POWER start date YYYY-MM-DD")
    parser.add_argument("--power-end", type=str, help="POWER end date YYYY-MM-DD")
    parser.add_argument(
        "--climate-preset",
        type=str,
        default=None,
        help="Climate preset name (e.g. netherlands_temperate)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="normal",
        choices=["normal", "drought", "wet", "hot", "cold"],
        help="Synthetic weather scenario",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for synthetic weather (default 42 for reproducibility)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Simulation start date YYYY-MM-DD (default: Jan 1 current year)",
    )


def _resolve_start_date(args: Any) -> _date:
    start_str = getattr(args, "start_date", None)
    if start_str:
        return _dt.strptime(start_str, "%Y-%m-%d").date()
    return _date(_date.today().year, 1, 1)


def _generate_synthetic(args: Any, days: int) -> WeatherSeries:
    from agrogame.weather.presets import load_climate_presets
    from agrogame.weather.generator import SyntheticWeatherGenerator

    preset_name = args.climate_preset
    lib = load_climate_presets()
    if preset_name not in lib.climates:
        raise ValueError(
            f"Unknown climate preset {preset_name!r}; "
            f"available: {sorted(lib.climates.keys())}"
        )
    scenario = getattr(args, "scenario", "normal")
    seed = getattr(args, "seed", 42)
    gen = SyntheticWeatherGenerator(lib.climates[preset_name], seed=seed)
    return gen.generate(days, _resolve_start_date(args), scenario)


def get_weather_series(args: Any, days: int) -> WeatherSeries | None:
    if getattr(args, "weather_file", None):
        return load_weather(args.weather_file)
    if getattr(args, "climate_preset", None):
        return _generate_synthetic(args, days)
    if getattr(args, "power_lat", None) is not None:
        if getattr(args, "power_start", None) and getattr(args, "power_end", None):
            start = _dt.strptime(args.power_start, "%Y-%m-%d").date()
            end = _dt.strptime(args.power_end, "%Y-%m-%d").date()
        else:
            today = _date.today()
            end = _date(today.year - 1, today.month, today.day)
            start = end - _td(days=days - 1)
        return load_weather_auto(args.power_lat, args.power_lon, start, end)
    return None
