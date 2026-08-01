"""Constants for sulfur module calculations."""

from __future__ import annotations

# Soil geometry/conversion (shared with nitrogen/phosphorus for consistency)
SOIL_AREA_M2_PER_HA: float = 10000.0
BULK_DENSITY_G_CM3_TO_KG_M3: float = 1000.0

# Organic matter to sulfur conversion (fraction of OM mass that is S).
# The vast majority (>90%) of topsoil S is held in organic matter, at a
# C:S ratio broadly parallel to (but wider than) C:N. A modest default of
# ~0.03% of OM mass as S sits within the reported range.
# Ref: Eriksen (2009) Adv. Agron. 102; Tabatabai & Bremner (1972) SSSAJ.
ORGANIC_MATTER_S_FRACTION: float = 0.0003

# pH anchor points for SO4 availability (dimensionless multiplier). Sulfate
# is far less pH-sensitive than phosphate — plant-available across a broad
# range — so the curve is near-flat over pH 5.5-8 and only tapers at extremes.
# Ref: Hawkesford & De Kok (2006) Plant Cell Environ. 29:382-395.
PH_AVAILABILITY_ANCHORS: tuple[tuple[float, float], ...] = (
    (3.5, 0.3),
    (4.5, 0.7),
    (5.5, 1.0),
    (8.0, 1.0),
    (9.0, 0.6),
)
