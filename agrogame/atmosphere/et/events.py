"""Evapotranspiration domain events emitted by the ET runtime."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class EvapotranspirationComputed(BaseEvent):
    """Diagnostic snapshot of the day's evapotranspiration partition.

    Emitted by :class:`~agrogame.atmosphere.et.runtime.ETRuntime` on the ``et``
    phase after the potential/actual split is resolved. Diagnostic-only
    (``*Computed`` per docs/conventions.md): it drives no state and exists so
    observers (e.g. the realism suite) can accumulate seasonal actual crop ET
    without reaching into runtime internals.

    Attributes:
        et0_mm: Reference evapotranspiration for the day (mm). Priestley-Taylor
            (Priestley & Taylor 1972; alpha = 1.26) on net radiation
            Rn = 0.6·Rs (ADR-014; FAO-56 Eqs. 38-40), not the FAO-56
            Penman-Monteith ET0: it has no aerodynamic (wind x VPD) term.
        evaporation_mm: Actual soil evaporation supplied this day (mm).
        transpiration_mm: Actual crop transpiration supplied this day (mm).
    """

    et0_mm: float
    evaporation_mm: float
    transpiration_mm: float
