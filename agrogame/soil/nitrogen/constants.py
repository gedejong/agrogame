"""Constants for nitrogen module calculations."""

from __future__ import annotations

# Soil geometry/conversion
SOIL_AREA_M2_PER_HA: float = 10000.0
BULK_DENSITY_G_CM3_TO_KG_M3: float = 1000.0

# Organic matter to nitrogen conversion (fraction of OM mass that is N)
ORGANIC_MATTER_N_FRACTION: float = 0.05

# NH4+/NH3 acid dissociation constant, pKa at 25 °C (Emerson et al. 1975,
# J. Fish. Res. Board Can. 32: 2379-2383)
NH3_PKA: float = 9.25
# pH of the hydrolysing urea band at the soil surface: the reference at which
# the volatilisation base rate applies (Sommer, Schjoerring & Denmead 2004)
UREA_BAND_REFERENCE_PH: float = 9.0
