"""Calendar-driven event types shared across all simulation modules.

Lives under ``agrogame.events`` (not ``agrogame.sim``) so that domain
runtimes can subscribe to ``DayTick`` without dragging the simulation
composition root into the dependency graph (#300, ADR-008).

``DayTick.drivers`` carries an optional ``DailyDrivers`` payload from the
soil-water package. To keep the ``events_isolated`` contract green, this
module does **not** import the type — the annotation is a forward
reference (string) resolved by static type checkers. ``dataclasses``
honours forward references unchanged because ``from __future__ import
annotations`` is in effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from agrogame.events import BaseEvent

Phase = Literal[
    "day_start",
    "chemistry",
    "water",
    "redox",
    "plant_structure",
    "et",
    "nutrients",
    "canopy",
    "day_end",
]


@dataclass(frozen=True)
class DayTick(BaseEvent):
    """One simulation day's tick, scoped by `phase` to fan out across modules."""

    sim_date: date
    phase: Phase
    # Forward reference — see module docstring for why we don't import.
    drivers: Any | None = None
    target_ph: float | None = None
    tmin_c: float | None = None
    tmax_c: float | None = None
    par_mj_m2: float | None = None
    plant_n_demand_kg_ha: float | None = None
    plant_p_demand_kg_ha: float | None = None
