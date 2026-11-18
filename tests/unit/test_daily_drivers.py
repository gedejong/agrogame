"""DailyDrivers as a frozen dataclass: same constructor, data not a repr (#562)."""

from __future__ import annotations

import dataclasses
import json
from datetime import date

import pytest

from agrogame.events.calendar import DayTick
from agrogame.soil.water.types import DailyDrivers


def test_negative_drivers_clamp_to_zero_as_before() -> None:
    d = DailyDrivers(
        rainfall_mm=-1.0,
        irrigation_mm=-2.0,
        evaporation_mm=-3.0,
        rainfall_intensity_mm_hr=-4.0,
    )
    assert (d.rainfall_mm, d.irrigation_mm, d.evaporation_mm) == (0.0, 0.0, 0.0)
    assert d.rainfall_intensity_mm_hr == 0.0


def test_positional_order_and_defaults_are_unchanged() -> None:
    d = DailyDrivers(5.0, 1.5, 2.5, 12.0)
    assert (d.rainfall_mm, d.irrigation_mm, d.evaporation_mm) == (5.0, 1.5, 2.5)
    assert d.rainfall_intensity_mm_hr == 12.0
    bare = DailyDrivers(rainfall_mm=3.0)
    assert (bare.irrigation_mm, bare.evaporation_mm) == (0.0, 0.0)
    assert bare.rainfall_intensity_mm_hr is None


def test_drivers_are_immutable() -> None:
    d = DailyDrivers(rainfall_mm=3.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.rainfall_mm = 9.0  # type: ignore[misc]


def test_day_tick_to_dict_renders_drivers_as_their_fields() -> None:
    """``to_dict`` feeds the emit debug log, ``EventRecorder`` and ``/step``."""
    tick = DayTick(
        sim_date=date(2024, 4, 1),
        phase="water",
        drivers=DailyDrivers(rainfall_mm=4.2, evaporation_mm=1.1),
    )
    data = tick.to_dict()
    assert data["drivers"] == {
        "rainfall_mm": 4.2,
        "irrigation_mm": 0.0,
        "evaporation_mm": 1.1,
        "rainfall_intensity_mm_hr": None,
    }
    assert " object at 0x" not in repr(tick)
    data.pop("sim_date")
    json.dumps(data)  # JSON-safe without a ``default`` hook
