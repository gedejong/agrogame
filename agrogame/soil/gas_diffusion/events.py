"""Gas diffusion domain events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class GasConcentrationUpdated(BaseEvent):
    """Gas concentrations computed for a soil layer (#217).

    Emitted once per layer per ``daily_step``. Concentrations are
    expressed as volume fractions (m3 gas / m3 soil air).

    Attributes:
        layer: Zero-based layer index.
        o2_frac: O2 volume fraction in soil air (0..1).
        co2_frac: CO2 volume fraction in soil air (0..1).
        anaerobic: True when air-filled porosity is below the critical
            threshold or O2 is below the anaerobic threshold.
        anaerobic_microsite_frac: Estimated fraction of the layer
            volume with O2 below the anaerobic threshold.
    """

    layer: int
    o2_frac: float
    co2_frac: float
    anaerobic: bool
    anaerobic_microsite_frac: float
