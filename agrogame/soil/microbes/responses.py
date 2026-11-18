from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class EnvironmentalResponses:
    """Lightweight temp/moisture/pH response modifiers.

    Calibrated to typical literature patterns:
    - Temperature: rises to an optimum ~30°C, declines toward ~45°C
    - Moisture (WFPS): optimum ~0.6, declines toward saturation and dryness
    - pH: 1.0 at pH >= 6.8, 2/3 at 4.5, 0 at 4.0 (Rousk et al. 2009, #553)

    Temperature and moisture shapes are placeholders until AGRO-70.
    """

    # Temperature triangular response (normalized 0..1)
    temp_min_c: float = 0.0
    temp_opt_c: float = 30.0
    temp_max_c: float = 45.0
    # Moisture optimum (WFPS fraction 0..1)
    moisture_opt_wfps: float = 0.6
    # pH response knots, pH in water (Rousk et al. 2009; see ph_modifier)
    ph_plateau: float = 6.8
    ph_inhibition: float = 4.5
    activity_at_inhibition: float = 2.0 / 3.0
    ph_zero_activity: float = 4.0

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
        """Microbial activity modifier (0..1) for soil pH; non-finite pH raises.

        Rousk, Brookes & Bååth 2009, Appl. Environ. Microbiol. 75:1589-1596,
        doi:10.1128/aem.02775-08 (Hoosfield acid strip, pH 8.3 to 4.0): basal
        respiration fell by only about one third down to pH 4.5; below 4.5 all
        microbial variables were inhibited. Hence linear 1.0 -> 2/3 from pH 6.8
        to 4.5, then -> 0 at 4.0 (acid end of the gradient), 0 below. Modelling
        choices, not data: the 1.0 plateau above 6.8 keeps the default-pH (6.8)
        baseline exact; the line to 0 at 4.0 reads "universal inhibition".
        """
        p = float(ph)
        if not math.isfinite(p):
            raise ValueError(f"soil pH must be finite, got {ph!r}")
        if p >= self.ph_plateau:
            return 1.0
        if p > self.ph_inhibition:
            drop = (self.ph_plateau - p) / (self.ph_plateau - self.ph_inhibition)
            return 1.0 - drop * (1.0 - self.activity_at_inhibition)
        if p > self.ph_zero_activity:
            span = self.ph_inhibition - self.ph_zero_activity
            return self.activity_at_inhibition * (p - self.ph_zero_activity) / span
        return 0.0
