"""Water model shared types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WaterFluxes:
    """Diagnostic fluxes and storage change for a daily step.

    Attributes:
        runoff_mm: Surface runoff (mm).
        deep_drainage_mm: Water lost below profile (mm).
        evap_mm: Actual evaporation taken (mm).
        storage_change_mm: Net change in soil water storage (mm).
    """

    runoff_mm: float
    deep_drainage_mm: float
    evap_mm: float
    storage_change_mm: float


class DailyDrivers:
    """Exogenous daily drivers for the water model.

    Args:
        rainfall_mm: Precipitation input (mm).
        irrigation_mm: Irrigation input (mm).
        evaporation_mm: Potential evaporation demand (mm).
        rainfall_intensity_mm_hr: Peak rainfall intensity during the day
            (mm/hr). Used by dual-porosity models (#213) to decide
            matrix vs macropore partitioning. When None, the estimate
            ``rainfall_mm / 24`` is used as a uniform-rate fallback.
    """

    def __init__(
        self,
        rainfall_mm: float,
        irrigation_mm: float = 0.0,
        evaporation_mm: float = 0.0,
        rainfall_intensity_mm_hr: float | None = None,
    ):
        """Initialize daily drivers with non-negative values."""
        self.rainfall_mm = max(0.0, rainfall_mm)
        self.irrigation_mm = max(0.0, irrigation_mm)
        self.evaporation_mm = max(0.0, evaporation_mm)
        self.rainfall_intensity_mm_hr: float | None = (
            max(0.0, rainfall_intensity_mm_hr)
            if rainfall_intensity_mm_hr is not None
            else None
        )
