"""Constants for sulfur module calculations."""

from __future__ import annotations

# Soil geometry/conversion (shared with nitrogen/phosphorus for consistency)
SOIL_AREA_M2_PER_HA: float = 10000.0
BULK_DENSITY_G_CM3_TO_KG_M3: float = 1000.0

# Organic matter to sulfur conversion (fraction of OM mass that is S).
# >90% of topsoil S is held in organic matter. Soil OM is ~58% C by mass,
# and the organic C:S ratio in temperate agricultural topsoils centres on
# ~70-100:1. At C:S ≈ 72.5:1 the S fraction of OM is 0.58 / 72.5 ≈ 0.008
# (0.007-0.008 spans C:S ~72-83:1). This yields ~200-260 mg S/kg for a 3%
# OM topsoil (pool(mg/kg) = 1e4 x OM% x fraction) and ~400 mg/kg at 5% OM —
# squarely in the literature 200-400 mg total-S/kg band. The previous
# default (0.0003) was ~25x too small (~9 mg/kg), which had been masked by
# a compensating ~25x too-fast (lab-incubation) mineralization rate (#386).
# Ref: Eriksen (2009) Adv. Agron. 102 (organic-S pools, C:N:S coupling);
# Scherer (2001) Eur. J. Agron. 14:81-111 (soil-S status, S response);
# Tabatabai & Bremner (1972) SSSAJ (C:N:S stoichiometry).
ORGANIC_MATTER_S_FRACTION: float = 0.008

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
