"""Constants for phosphorus module calculations."""

from __future__ import annotations

# Soil geometry/conversion (shared with nitrogen for consistency)
SOIL_AREA_M2_PER_HA: float = 10000.0
BULK_DENSITY_G_CM3_TO_KG_M3: float = 1000.0

# Organic matter to phosphorus conversion (fraction of OM mass that is P)
# Literature ranges roughly 0.1–0.5% of OM as P; pick a modest default.
ORGANIC_MATTER_P_FRACTION: float = 0.002

# pH anchor points for availability (dimensionless multiplier)
PH_AVAILABILITY_ANCHORS: tuple[tuple[float, float], ...] = (
    (4.0, 0.0),
    (5.0, 0.5),
    (6.5, 1.0),
    (7.0, 1.0),
    (8.0, 0.7),
    (9.0, 0.0),
)

# Weekly fixation fraction bounds (1–5% per week) to scale by pH
FIXATION_WEEKLY_MIN: float = 0.01
FIXATION_WEEKLY_MAX: float = 0.05

# Heavy drainage threshold for minimal P movement (mm/day)
HEAVY_DRAINAGE_MM: float = 50.0

# Fraction of available P that may move under heavy drainage (very small)
HEAVY_DRAINAGE_P_FRACTION: float = 0.001
