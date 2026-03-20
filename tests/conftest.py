"""Shared test fixtures for the agrogame test suite."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from agrogame.weather.types import WeatherRecord, WeatherSeries


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def event_bus_debug() -> EventBus:
    return EventBus(debug_mode=True)


@pytest.fixture
def soil_profile() -> SoilProfile:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    return lib.soils["loam_temperate"]


@pytest.fixture
def weather_records() -> WeatherSeries:
    return WeatherSeries(
        [
            WeatherRecord(
                day=date(2024, 6, d),
                tmin_c=10 + d,
                tmax_c=22 + d,
                relative_humidity_pct=60.0,
                wind_m_s=2.5,
                shortwave_mj_m2=18.0,
                net_radiation_mj_m2=14.0,
                precip_mm=3.0,
            )
            for d in range(1, 8)
        ]
    )
