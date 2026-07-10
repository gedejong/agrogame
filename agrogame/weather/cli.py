from __future__ import annotations

import logging
from argparse import ArgumentParser
from datetime import date as _date, timedelta as _td
from datetime import datetime as _dt
from pathlib import Path
from typing import Any

from agrogame.weather import load_weather, load_weather_auto
from agrogame.weather.types import WeatherSeries

_qa_logger = logging.getLogger("agrogame.weather.qa")


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
    parser.add_argument(
        "--weather-qa",
        action="store_true",
        help="run weather QA on file-based series and log a summary (warn-only)",
    )
    parser.add_argument(
        "--weather-qa-repair",
        action="store_true",
        help="repair the file-based series after QA (implies --weather-qa)",
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


def _run_weather_qa(args: Any, series: WeatherSeries) -> WeatherSeries:
    """Run QA on a file-based series; log a summary and optionally repair.

    Default is warn-only (no mutation); repair happens only when
    ``--weather-qa-repair`` is set.
    """
    from agrogame.weather.qa import (
        Severity,
        log_anomalies,
        repair_weather_series,
        validate_weather_series,
    )

    report = validate_weather_series(series)
    counts = report.counts_by_severity()
    _qa_logger.warning(
        "weather QA: %d record(s), %d anomaly(ies) "
        "(errors: %d, warnings: %d, info: %d)",
        report.n_records,
        report.n_anomalies,
        counts[Severity.ERROR],
        counts[Severity.WARNING],
        counts[Severity.INFO],
    )
    log_anomalies(report)
    if getattr(args, "weather_qa_repair", False):
        repaired, actions = repair_weather_series(series)
        _qa_logger.warning("weather QA: applied %d repair(s)", len(actions))
        return repaired
    return series


def get_weather_series(args: Any, days: int) -> WeatherSeries | None:
    if getattr(args, "weather_file", None):
        series = load_weather(args.weather_file)
        if getattr(args, "weather_qa", False) or getattr(
            args, "weather_qa_repair", False
        ):
            series = _run_weather_qa(args, series)
        return series
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
