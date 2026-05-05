"""Mutable gas diffusion state per soil layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GasDiffusionState:
    """Per-layer gas concentrations and anaerobic flags.

    Concentrations are volume fractions in the soil air phase (m3 gas
    per m3 of air-filled pore space). They are initialized to
    atmospheric at all depths and converge toward the steady-state
    profile once ``daily_step`` is called.
    """

    o2_frac: list[float] = field(default_factory=list)
    co2_frac: list[float] = field(default_factory=list)
    anaerobic: list[bool] = field(default_factory=list)
    anaerobic_microsite_frac: list[float] = field(default_factory=list)

    @classmethod
    def from_layers(
        cls,
        n_layers: int,
        atmospheric_o2_frac: float = 0.2095,
        atmospheric_co2_frac: float = 0.00042,
    ) -> GasDiffusionState:
        """Initialize state with atmospheric-equilibrium profile."""
        return cls(
            o2_frac=[atmospheric_o2_frac] * n_layers,
            co2_frac=[atmospheric_co2_frac] * n_layers,
            anaerobic=[False] * n_layers,
            anaerobic_microsite_frac=[0.0] * n_layers,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "o2_frac": list(self.o2_frac),
            "co2_frac": list(self.co2_frac),
            "anaerobic": list(self.anaerobic),
            "anaerobic_microsite_frac": list(self.anaerobic_microsite_frac),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GasDiffusionState:
        return cls(
            o2_frac=list(data.get("o2_frac", [])),
            co2_frac=list(data.get("co2_frac", [])),
            anaerobic=list(data.get("anaerobic", [])),
            anaerobic_microsite_frac=list(data.get("anaerobic_microsite_frac", [])),
        )
