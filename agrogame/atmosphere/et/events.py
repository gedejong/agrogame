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
        et0_mm: Reference evapotranspiration for the day (mm). NOTE: the model's
            Priestley-Taylor ET0 is *not* FAO-56-calibrated — it treats full
            shortwave as net radiation, so it runs ~2-4× the FAO-56 range
            (tracked separately, #414/#418). Do not bound this against FAO-56.
        evaporation_mm: Actual soil evaporation supplied this day (mm).
        transpiration_mm: Actual crop transpiration supplied this day (mm).
    """

    et0_mm: float
    evaporation_mm: float
    transpiration_mm: float
