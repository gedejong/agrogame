"""Default micronutrient pool sizes and pH-availability lookup tables.

Literature sources:
- Lindsay 1979, Chemical Equilibria in Soils
- Alloway 2008, Micronutrient Deficiencies in Global Crop Production
- Marschner 2012, Mineral Nutrition of Higher Plants (3rd ed.)
"""

from __future__ import annotations

# Default total pools (mg/kg soil, i.e., ppm) per layer.
# Typical agricultural soils (Lindsay 1979).
DEFAULT_TOTAL_FE_PPM = 25000.0  # total Fe is abundant, availability is the issue
DEFAULT_TOTAL_ZN_PPM = 60.0
DEFAULT_TOTAL_MN_PPM = 600.0

# Default DTPA-extractable (plant-available) fractions.
# Fraction of total that is initially available.
DEFAULT_AVAIL_FRACTION_FE = 0.0004  # ~10 ppm DTPA-Fe
DEFAULT_AVAIL_FRACTION_ZN = 0.02  # ~1.2 ppm DTPA-Zn
DEFAULT_AVAIL_FRACTION_MN = 0.03  # ~18 ppm DTPA-Mn

# Critical deficiency levels (ppm DTPA-extractable).
# Below these, stress < 1.0. Ref: Sims & Johnson 1991.
CRITICAL_FE_PPM = 4.5
CRITICAL_ZN_PPM = 0.8
CRITICAL_MN_PPM = 1.0

# Toxicity thresholds (ppm). Above these, toxicity stress.
# Ref: Marschner 2012; Foy et al. 1978.
TOXIC_FE_PPM = 300.0  # Fe toxicity in flooded/acid soils
TOXIC_ZN_PPM = 100.0
TOXIC_MN_PPM = 100.0

# pH-availability multipliers (piecewise-linear).
# Each entry: (pH, multiplier). Interpolate between points.
# Fe availability drops sharply above pH 6.5 (Lindsay 1979).
PH_AVAIL_FE = [(4.0, 1.5), (5.5, 1.2), (6.5, 1.0), (7.5, 0.3), (8.5, 0.05)]
# Zn drops above pH 7.0 (Alloway 2008).
PH_AVAIL_ZN = [(4.0, 1.3), (5.5, 1.1), (7.0, 1.0), (7.5, 0.5), (8.5, 0.15)]
# Mn drops above pH 7.0 (Lindsay 1979).
PH_AVAIL_MN = [(4.0, 2.0), (5.5, 1.5), (6.5, 1.0), (7.5, 0.4), (8.5, 0.1)]

# Plant demand (g/ha/season). Ref: Marschner 2012, Table 9.1.
# These are total-season demands; daily demand is computed from growth rate.
DEFAULT_DEMAND_FE_G_HA = 300.0
DEFAULT_DEMAND_ZN_G_HA = 150.0
DEFAULT_DEMAND_MN_G_HA = 200.0

# Soil bulk density for ppm → g/ha conversion (typical loam).
BULK_DENSITY_KG_M3 = 1300.0
DEFAULT_LAYER_DEPTH_CM = 30.0

# Conversion factor: ppm (mg/kg) ↔ g/ha for a single layer.
# soil_mass = bulk_density * depth_m * 10_000 m²/ha = 3,900,000 kg
# 1 ppm = 1 mg/kg = 3,900,000 mg = 3,900 g per ha
# So: g/ha = ppm * PPM_TO_G_HA; ppm = g/ha / PPM_TO_G_HA
PPM_TO_G_HA = BULK_DENSITY_KG_M3 * (DEFAULT_LAYER_DEPTH_CM / 100.0) * 10_000 / 1_000
