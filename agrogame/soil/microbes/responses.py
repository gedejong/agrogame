from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EnvironmentalResponses:
    """Lightweight temp/moisture/pH response modifiers.

    Calibrated to typical literature patterns:
    - Temperature: rises to an optimum ~30°C, declines toward ~45°C
    - Moisture (WFPS): optimum ~0.6, declines toward saturation and dryness
    - pH: peak near neutral (~6.8), symmetric decline with width ~1.5 pH units

    Placeholder shapes until AGRO-70 provides validated response surfaces.
    """

    # Temperature triangular response (normalized 0..1)
    temp_min_c: float = 0.0
    temp_opt_c: float = 30.0
    temp_max_c: float = 45.0
    # Moisture optimum (WFPS fraction 0..1)
    moisture_opt_wfps: float = 0.6
    # pH response parameters
    ph_opt: float = 6.8
    ph_width: float = 1.5

    def temperature_modifier(self, temperature_c: float) -> float:
        # Piecewise linear peak at temp_opt_c; 0 outside [temp_min_c, temp_max_c]
        t = float(temperature_c)
        if t <= self.temp_min_c or t >= self.temp_max_c:
            return 0.0
        if t <= self.temp_opt_c:
            return float(
                (t - self.temp_min_c) / max(1e-6, (self.temp_opt_c - self.temp_min_c))
            )
        return float(
            (self.temp_max_c - t) / max(1e-6, (self.temp_max_c - self.temp_opt_c))
        )

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

    def ph_modifier(self, ph: float) -> float:
        # Triangular peak at ph_opt with full width ph_width (0 at edges)
        diff = abs(float(ph) - self.ph_opt)
        if diff >= self.ph_width:
            return 0.0
        return float(1.0 - diff / max(1e-6, self.ph_width))
