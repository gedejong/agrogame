"""EventBus.unsubscribe: retiring one observer while the bus lives on (#486)."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus


@dataclass
class _Ping:
    value: int


class _Observer:
    def __init__(self) -> None:
        self.seen: list[int] = []

    def on_ping(self, ev: _Ping) -> None:
        self.seen.append(ev.value)


def test_unsubscribe_stops_delivery_to_that_handler_only() -> None:
    bus = EventBus()
    retired, kept = _Observer(), _Observer()
    bus.subscribe(_Ping, retired.on_ping)
    bus.subscribe(_Ping, kept.on_ping)
    assert bus.unsubscribe(_Ping, retired.on_ping) is True
    bus.emit(_Ping(1))
    assert retired.seen == []
    assert kept.seen == [1]


def test_unsubscribe_accepts_a_fresh_bound_method_reference() -> None:
    bus = EventBus()
    obs = _Observer()
    bus.subscribe(_Ping, obs.on_ping)
    # obs.on_ping creates a new bound-method object each access; equality,
    # not identity, is what makes a later unsubscribe work.
    assert bus.unsubscribe(_Ping, obs.on_ping) is True
    assert bus._handlers[_Ping] == []


def test_unsubscribe_removes_one_registration_per_call() -> None:
    bus = EventBus()
    obs = _Observer()
    bus.subscribe(_Ping, obs.on_ping)
    bus.subscribe(_Ping, obs.on_ping)
    bus.unsubscribe(_Ping, obs.on_ping)
    bus.emit(_Ping(7))
    assert obs.seen == [7]


def test_unsubscribe_absent_handler_returns_false() -> None:
    bus = EventBus()
    obs = _Observer()
    assert bus.unsubscribe(_Ping, obs.on_ping) is False
    bus.subscribe(_Ping, obs.on_ping)
    bus.clear()  # e.g. a crop reset tore the whole bus down first
    assert bus.unsubscribe(_Ping, obs.on_ping) is False
