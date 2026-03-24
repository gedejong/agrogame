"""Thin wrapper delegating to agrogame.weather.cli."""

from __future__ import annotations

from agrogame.weather.cli import add_weather_args, get_weather_series

__all__ = ["add_weather_args", "get_weather_series"]
