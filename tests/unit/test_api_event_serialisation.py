"""``/step`` event payloads are data, never Python reprs (#562).

``_serialize_events`` only reads ``patch.recorder.events``, so these tests feed
it a real ``EventRecorder`` on a bare bus instead of a simulated patch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

from agrogame.api.routes import _serialize_events  # noqa: E402
from agrogame.events import BaseEvent, EventBus  # noqa: E402
from agrogame.events.calendar import DayTick  # noqa: E402
from agrogame.events.recorder import EventRecorder  # noqa: E402
from agrogame.params.phenology import PhenologyStage  # noqa: E402
from agrogame.soil.phenology.events import StageChanged  # noqa: E402
from agrogame.soil.water.types import DailyDrivers  # noqa: E402


class _Sentinel:
    """A plain object: ``json`` cannot encode it and ``str`` would be a repr."""


@dataclass(frozen=True)
class _OpaquePayload(BaseEvent):
    blob: Any = None


def _serialised(*events: BaseEvent) -> list[dict]:
    bus = EventBus()
    recorder = EventRecorder(bus)
    for ev in events:
        bus.emit(ev)
    return _serialize_events(SimpleNamespace(recorder=recorder))


def test_day_tick_drivers_and_date_serialise_as_data() -> None:
    [water, canopy] = _serialised(
        DayTick(
            sim_date=date(2024, 4, 1),
            phase="water",
            drivers=DailyDrivers(rainfall_mm=6.5, irrigation_mm=2.0),
        ),
        DayTick(sim_date=date(2024, 4, 1), phase="canopy"),
    )
    assert water["event_type"] == "DayTick"
    assert water["data"]["sim_date"] == "2024-04-01"
    assert water["data"]["drivers"] == {
        "rainfall_mm": 6.5,
        "irrigation_mm": 2.0,
        "evaporation_mm": 0.0,
        "rainfall_intensity_mm_hr": None,
    }
    assert canopy["data"]["drivers"] is None


def test_stage_changed_stages_serialise_as_enum_values() -> None:
    """``"emerged"``, as ``crop_stage`` reports it, not ``PhenologyStage.EMERGED``."""
    [ev] = _serialised(
        StageChanged(
            from_stage=PhenologyStage.PLANTED,
            to_stage=PhenologyStage.EMERGED,
            at_gdd=82.5,
        )
    )
    assert ev["data"] == {
        "from_stage": "planted",
        "to_stage": "emerged",
        "at_gdd": 82.5,
    }


def test_wall_clock_timestamp_is_not_serialised() -> None:
    """``BaseEvent.timestamp`` is emit wall-clock time; it stays off the wire."""
    tick = DayTick(sim_date=date(2024, 4, 1), phase="day_start")
    assert "timestamp" in tick.to_dict()  # the recorder and debug log keep it
    [ev] = _serialised(tick)
    assert "timestamp" not in ev["data"]


def test_unknown_payload_type_raises_instead_of_leaking_a_repr() -> None:
    with pytest.raises(TypeError, match="_Sentinel has no JSON form"):
        _serialised(_OpaquePayload(blob=_Sentinel()))
