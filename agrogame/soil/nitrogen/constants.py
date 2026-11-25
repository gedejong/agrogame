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

# --- Uptake residual (#694, ADR-013 amendment 2026-11-25) -------------------
# Roots cannot draw a layer's mineral N below a residual concentration, in mg N
# per kg soil. CERES-Maize caps each layer's uptake at SNO3 - 0.25/KG2PPM and
# SNH4 - 0.5/KG2PPM, with KG2PPM = 10/(BD*DLAYR) (DSSAT-CSM v4.8.6.0
# Plant/CERES-Maize/MZ_NUPTAK.for:211-214, the XMIN terms). CERES-Sorghum
# (SG_NUPTAK.for:207-210) and CROPGRO (Plant/CROPGRO/NUPTAK.for:170-177) use
# the same values. Jones et al. 2003, Eur. J. Agron. 18:235-265.
NO3_UPTAKE_RESIDUAL_MG_KG: float = 0.25
NH4_UPTAKE_RESIDUAL_MG_KG: float = 0.5

# Molar mass of nitrogen, kg N per kmol N: the IUPAC conventional standard
# atomic weight 14.007 (Meija et al. 2016, Pure Appl. Chem. 88:265-291).
N_KG_PER_KMOL: float = 14.007

# --- Proton budget of the N cycle (#492, ADR-020) ---------------------------
# Signed H+ released into the soil per mol N transformed (+ acidifies,
# - alkalinises). Bolan, Hedley & White 1991, Plant Soil 134:53-63,
# doi:10.1007/bf00010717; Helyar & Porter 1989, in Robson (ed.) Soil Acidity
# and Plant Growth, pp. 61-101, doi:10.1016/b978-0-12-590655-5.50007-4.
#
#   process                                   reaction                       H+/N
#   urea hydrolysis                           CO(NH2)2 + 2H2O + 2H+          -1
#                                               -> 2NH4+ + CO2
#   ammonification (organic N -> NH4+)        R-NH2 + H2O + H+ -> R-OH+NH4+  -1
#   nitrification                             NH4+ + 2O2 -> NO3- + H2O + 2H+ +2
#   NO3- uptake (root releases OH-/HCO3-)                                    -1
#   NH4+ uptake (root releases H+)                                           +1
#   denitrification                           NO3- + H+ -> 1/2 N2 (+ N2O)    -1
#   NH3 volatilisation                        NH4+ -> NH3(g) + H+            +1
#
# Ammonium nitrate adds NH4+ and NO3- as a neutral salt: no term at
# application. Nitrate leaching needs no term: the H+ stays in the layer
# where the nitrate was produced (Helyar & Porter 1989).
H_PER_N_UREA_HYDROLYSIS: float = -1.0
H_PER_N_AMMONIFICATION: float = -1.0
H_PER_N_NITRIFICATION: float = 2.0
H_PER_N_NO3_UPTAKE: float = -1.0
H_PER_N_NH4_UPTAKE: float = 1.0
H_PER_N_DENITRIFICATION: float = -1.0
H_PER_N_VOLATILIZATION: float = 1.0
