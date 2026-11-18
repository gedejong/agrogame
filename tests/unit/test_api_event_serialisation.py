"""``/step`` event payloads are data, never Python reprs (#562).

``_serialize_events`` only reads ``patch.recorder.events``, so these tests feed
it a real ``EventRecorder`` on a bare bus instead of a simulated patch.

``/step`` raises on a payload value with no JSON form, so every event type the
engine defines is discovered and serialised here: a new type with such a field
fails in CI, not in the middle of a season.
"""

from __future__ import annotations

import importlib
import pkgutil
import types
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import PurePath
from types import SimpleNamespace
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

import pytest

pytest.importorskip("fastapi")

import agrogame  # noqa: E402
from agrogame.api.routes import _serialize_events  # noqa: E402
from agrogame.events import BaseEvent, EventBus  # noqa: E402
from agrogame.events.calendar import DayTick  # noqa: E402
from agrogame.events.recorder import EventRecorder  # noqa: E402
from agrogame.params.phenology import PhenologyStage  # noqa: E402
from agrogame.soil.phenology.events import StageChanged  # noqa: E402
from agrogame.soil.water.types import DailyDrivers  # noqa: E402

# Dashboard extras (``poetry install -E dashboard``); a module needing them is
# skipped when they are absent. Any other import failure fails discovery.
_OPTIONAL_DEPS = {"streamlit", "plotly"}
# Event types that never reach /step, each with the reason.
_OFF_STEP_EVENTS = {
    "agrogame.config.events.ConfigReloaded": "emitted only by the config CLI's "
    "`watch` command, on a bus it creates itself, never on a patch bus",
}
# Samples for fields whose annotation cannot supply one (``Any``). A sample
# cannot dodge the check: a value with no JSON form still fails to serialise.
_FIELD_SAMPLES: dict[tuple[str, str], object] = {
    ("DayTick", "drivers"): DailyDrivers(rainfall_mm=4.0, irrigation_mm=1.0),
}
# The count on main at #562: a floor, so a discovery that finds nothing fails.
_MIN_EVENT_TYPES = 67
# ``bool`` before ``int`` and ``datetime`` before ``date``: subclasses first.
_SCALARS: tuple[tuple[type, object], ...] = (
    (bool, True),
    (int, 1),
    (float, 0.5),
    (str, "x"),
    (datetime, datetime(2024, 4, 1, 6)),
    (date, date(2024, 4, 1)),
)


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


def _dotted(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _engine_event_types() -> list[type[BaseEvent]]:
    """Every ``BaseEvent`` subclass under ``agrogame``, found by import, not by list."""
    for mod in pkgutil.walk_packages(agrogame.__path__, "agrogame."):
        try:
            importlib.import_module(mod.name)
        except ModuleNotFoundError as exc:
            if (exc.name or "").split(".")[0] not in _OPTIONAL_DEPS:
                raise
    found: set[type[BaseEvent]] = set()
    pending: list[type[BaseEvent]] = [BaseEvent]
    while pending:
        for sub in pending.pop().__subclasses__():
            if sub not in found:
                found.add(sub)
                pending.append(sub)
    engine = (c for c in found if c.__module__.startswith("agrogame."))
    return sorted(engine, key=_dotted)


def _sample(tp: Any, where: str) -> object:
    """A representative value of annotation ``tp``, for field ``where``."""
    origin, args = get_origin(tp), get_args(tp)
    if origin is Literal:
        return args[0]
    if origin in (Union, types.UnionType):
        return _sample(next(a for a in args if a is not type(None)), where)
    if origin is list:
        return [_sample(args[0], where)]
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return (_sample(args[0], where),)
        return tuple(_sample(a, where) for a in args)
    if origin is dict:
        return {_sample(args[0], where): _sample(args[1], where)}
    if isinstance(tp, type):
        if issubclass(tp, Enum):
            return next(iter(tp))
        if is_dataclass(tp):
            return _instance(tp)
        if issubclass(tp, PurePath):
            return tp("data/sample.yaml")
        for kind, value in _SCALARS:
            if issubclass(tp, kind):
                return value
    raise TypeError(f"no sample for {where}: {tp!r}; add one to _FIELD_SAMPLES")


def _instance(cls: type) -> Any:
    """``cls`` with every init field set from its annotation (``None`` avoided)."""
    hints = get_type_hints(cls)
    kwargs: dict[str, object] = {}
    for f in fields(cls):
        if not f.init:
            continue
        key = (cls.__name__, f.name)
        where = f"{cls.__name__}.{f.name}"
        kwargs[f.name] = (
            _FIELD_SAMPLES[key]
            if key in _FIELD_SAMPLES
            else _sample(hints[f.name], where)
        )
    return cls(**kwargs)


_EVENT_TYPES = _engine_event_types()


def test_event_type_discovery_is_not_vacuous() -> None:
    assert len(_EVENT_TYPES) >= _MIN_EVENT_TYPES
    assert set(_OFF_STEP_EVENTS) <= {_dotted(c) for c in _EVENT_TYPES}


@pytest.mark.parametrize(
    "event_type",
    [c for c in _EVENT_TYPES if _dotted(c) not in _OFF_STEP_EVENTS],
    ids=lambda c: _dotted(c).removeprefix("agrogame."),
)
def test_every_event_type_serialises_through_step(event_type: type) -> None:
    [out] = _serialised(_instance(event_type))
    assert out["event_type"] == event_type.__name__
    assert out["module"] == event_type.__module__
    assert set(out["data"]) == {f.name for f in fields(event_type)} - {"timestamp"}
