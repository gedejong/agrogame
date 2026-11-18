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


@dataclass(frozen=True)
class DailyDrivers:
    """Exogenous daily drivers for the water model.

    A frozen dataclass so that ``DayTick.to_dict()`` (``dataclasses.asdict``)
    renders it as a plain object of its fields. As a plain class it reached the
    ``/step`` event stream, the emit debug log and ``EventRecorder`` as its
    repr, memory address included (#562).

    Args:
        rainfall_mm: Precipitation input (mm).
        irrigation_mm: Irrigation input (mm).
        evaporation_mm: Potential evaporation demand (mm).
        rainfall_intensity_mm_hr: Peak rainfall intensity during the day
            (mm/hr). No water model currently reads it: its only consumer,
            the dual-porosity model, was retired (#466, ADR-016). Kept for
            preferential flow v2 (#485). ``None`` means no intensity known.
    """

    rainfall_mm: float
    irrigation_mm: float = 0.0
    evaporation_mm: float = 0.0
    rainfall_intensity_mm_hr: float | None = None

    def __post_init__(self) -> None:
        """Clamp every driver to be non-negative, as the constructor always has."""
        object.__setattr__(self, "rainfall_mm", max(0.0, self.rainfall_mm))
        object.__setattr__(self, "irrigation_mm", max(0.0, self.irrigation_mm))
        object.__setattr__(self, "evaporation_mm", max(0.0, self.evaporation_mm))
        if self.rainfall_intensity_mm_hr is not None:
            object.__setattr__(
                self,
                "rainfall_intensity_mm_hr",
                max(0.0, self.rainfall_intensity_mm_hr),
            )
