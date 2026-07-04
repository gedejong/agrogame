"""Weather drivers — historical loaders, climate presets, synthetic generator.

Docs: https://github.com/gedejong/agrogame/blob/main/docs/weather.md
"""

from .types import WeatherRecord, WeatherSeries
from .loader import load_weather, load_weather_auto
from .presets import ClimatePreset, ClimateLibrary, load_climate_presets
from .generator import SyntheticWeatherGenerator
from .utils import photoperiod_h, interpolate_weather_series
from .qa import (
    QAFinding,
    QAReport,
    RepairAction,
    Severity,
    repair_weather_series,
    validate_weather_series,
)

__all__ = [
    "WeatherRecord",
    "WeatherSeries",
    "load_weather",
    "load_weather_auto",
    "ClimatePreset",
    "ClimateLibrary",
    "load_climate_presets",
    "SyntheticWeatherGenerator",
    "photoperiod_h",
    "interpolate_weather_series",
    "QAFinding",
    "QAReport",
    "RepairAction",
    "Severity",
    "validate_weather_series",
    "repair_weather_series",
]
