from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EnvironmentalResponses:
    """Lightweight temp/moisture/pH response modifiers.

    Placeholder to be replaced by AGRO-70 response surfaces when available.
    """

    q10: float = 2.0
    moisture_opt_wfps: float = 0.6  # water-filled pore space (0-1)

    def temperature_modifier(
        self, temperature_c: float, reference_c: float = 20.0
    ) -> float:
        return float(self.q10 ** ((temperature_c - reference_c) / 10.0))

    def moisture_modifier(self, wfps: float) -> float:
        # Triangular response with optimum at moisture_opt_wfps
        if wfps <= 0.0:
            return 0.0
        if wfps >= 1.0:
            return 0.0
        if wfps <= self.moisture_opt_wfps:
            return float(wfps / self.moisture_opt_wfps)
        # decline after optimum
        return float(
            1.0 - (wfps - self.moisture_opt_wfps) / (1.0 - self.moisture_opt_wfps)
        )

    def ph_modifier(self, ph: float, optimum: float = 6.8, width: float = 1.5) -> float:
        # Simple bell-shaped response around optimum
        diff = abs(ph - optimum)
        if diff >= width:
            return 0.5
        return float(1.0 - 0.5 * (diff / width))
