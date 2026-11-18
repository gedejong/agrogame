"""EventBus dispatch and handler-error propagation (#606).

A handler exception used to be logged at DEBUG and swallowed, so a crashing
simulation handler silently dropped that day's physics. Every handler error now
propagates out of ``emit`` as ``EventHandlerError`` naming the handler and the
event type, chained from the original.
"""

from __future__ import annotations

import functools
import inspect
import logging
from dataclasses import dataclass

import pytest

from agrogame.events import BaseEvent, EventBus, EventHandlerError


@dataclass(frozen=True)
class _Outer(BaseEvent):
    value: int = 0


@dataclass(frozen=True)
class _Inner(BaseEvent):
    value: int = 0


@dataclass
class _Plain:
    """A non-BaseEvent payload: catch-alls never see it."""

    value: int = 0


class _Unloggable(BaseEvent):
    """An event whose ``to_dict`` itself fails."""

    def to_dict(self) -> dict[str, object]:
        raise TypeError("no dict form")

    def __str__(self) -> str:
        return "unloggable"


class _Recorder:
    def __init__(self) -> None:
        self.seen: list[object] = []

    def on_event(self, ev: object) -> None:
        self.seen.append(ev)


class _Failing:
    def on_outer(self, ev: _Outer) -> None:
        raise ValueError(f"bad value {ev.value}")


def _raise_key_error(ev: object) -> None:
    raise KeyError("missing")


def test_exact_type_handler_error_propagates_named_and_chained() -> None:
    bus = EventBus()
    bus.subscribe(_Outer, _Failing().on_outer)

    with pytest.raises(EventHandlerError) as info:
        bus.emit(_Outer(3))

    exc = info.value
    assert isinstance(exc, RuntimeError)
    assert exc.handler == f"{__name__}._Failing.on_outer"
    assert exc.event_type == "_Outer"
    assert isinstance(exc.__cause__, ValueError)
    assert str(exc.__cause__) == "bad value 3"
    message = str(exc)
    assert exc.handler in message
    assert "_Outer" in message
    assert "ValueError" in message
    # The original message stays in the chained cause, out of str(exc), which
    # the API returns to clients.
    assert "bad value" not in message


def test_catch_all_handler_error_propagates() -> None:
    bus = EventBus()
    exact = _Recorder()
    bus.subscribe(_Outer, exact.on_event)
    bus.subscribe(BaseEvent, _raise_key_error)

    event = _Outer(1)

    with pytest.raises(EventHandlerError) as info:
        bus.emit(event)

    assert info.value.handler == f"{__name__}._raise_key_error"
    assert info.value.event_type == "_Outer"
    assert isinstance(info.value.__cause__, KeyError)
    # Exact-type subscribers run before the catch-alls.
    assert exact.seen == [event]


def test_handlers_after_the_failing_one_are_not_called() -> None:
    bus = EventBus()
    before, after, catch_all = _Recorder(), _Recorder(), _Recorder()
    bus.subscribe(_Outer, before.on_event)
    bus.subscribe(_Outer, _Failing().on_outer)
    bus.subscribe(_Outer, after.on_event)
    bus.subscribe(BaseEvent, catch_all.on_event)

    event = _Outer(2)

    with pytest.raises(EventHandlerError):
        bus.emit(event)

    assert before.seen == [event]
    assert after.seen == []
    assert catch_all.seen == []


def test_innermost_handler_wins_on_nested_emit() -> None:
    bus = EventBus()

    def on_inner(ev: _Inner) -> None:
        raise ZeroDivisionError("inner failed")

    def on_outer(ev: _Outer) -> None:
        bus.emit(_Inner(ev.value))

    bus.subscribe(_Inner, on_inner)
    bus.subscribe(_Outer, on_outer)

    with pytest.raises(EventHandlerError) as info:
        bus.emit(_Outer(5))

    exc = info.value
    assert exc.handler.endswith("on_inner")
    assert "on_outer" not in exc.handler
    assert exc.event_type == "_Inner"
    assert isinstance(exc.__cause__, ZeroDivisionError)
    assert "_Outer" not in str(exc)


def test_handler_without_qualname_is_named_by_repr() -> None:
    bus = EventBus()
    handler = functools.partial(_raise_key_error)
    bus.subscribe(_Plain, handler)

    with pytest.raises(EventHandlerError) as info:
        bus.emit(_Plain(1))

    assert info.value.handler == repr(handler)
    assert info.value.event_type == "_Plain"


def test_plain_payload_reaches_exact_subscribers_only() -> None:
    bus = EventBus()
    exact, catch_all = _Recorder(), _Recorder()
    bus.subscribe(_Plain, exact.on_event)
    bus.subscribe(BaseEvent, catch_all.on_event)

    bus.emit(_Plain(4))

    assert exact.seen == [_Plain(4)]
    assert catch_all.seen == []


def test_emit_with_no_subscribers_is_a_no_op() -> None:
    EventBus().emit(_Outer(0))


def test_failing_to_dict_falls_back_to_str_and_still_delivers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Building the debug-log payload is not a handler call: its failure is
    # logged as the event's str and delivery goes on.
    bus = EventBus()
    seen = _Recorder()
    bus.subscribe(_Unloggable, seen.on_event)
    event = _Unloggable()

    with caplog.at_level(logging.DEBUG, logger="agrogame.events.bus"):
        bus.emit(event)

    assert seen.seen == [event]
    emitted = [r for r in caplog.records if r.getMessage() == "event_bus.emit"]
    assert [r.__dict__["event"] for r in emitted] == [{"event": "unloggable"}]


def test_bus_constructor_takes_no_arguments() -> None:
    # Isolation is gone (#606): there is no lenient mode to switch on.
    assert list(inspect.signature(EventBus).parameters) == []


def test_unsubscribe_and_clear_stop_delivery() -> None:
    # Full contract in tests/unit/test_event_bus_unsubscribe.py (#486); here so
    # this module alone covers bus.py.
    bus = EventBus()
    retired, cleared = _Recorder(), _Recorder()
    bus.subscribe(_Outer, retired.on_event)
    assert bus.unsubscribe(_Outer, retired.on_event) is True
    assert bus.unsubscribe(_Outer, retired.on_event) is False
    bus.subscribe(_Outer, cleared.on_event)
    bus.clear()

    bus.emit(_Outer(6))

    assert retired.seen == []
    assert cleared.seen == []
