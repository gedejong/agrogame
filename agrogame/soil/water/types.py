from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WaterFluxes:
    runoff_mm: float
    deep_drainage_mm: float
    evap_mm: float
    storage_change_mm: float


class DailyDrivers:
    def __init__(
        self,
        rainfall_mm: float,
        irrigation_mm: float = 0.0,
        evaporation_mm: float = 0.0,
    ):
        self.rainfall_mm = max(0.0, rainfall_mm)
        self.irrigation_mm = max(0.0, irrigation_mm)
        self.evaporation_mm = max(0.0, evaporation_mm)
