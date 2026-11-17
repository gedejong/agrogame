"""Immutable soil chemistry parameters.

Holds the base pH, the daily buffering rate and target, the per-event
pH increments and clamping bounds, and the pH buffer-capacity coefficients
used by :class:`SoilChemistryModule`. Extracted from hard-coded constants in
``module.py`` (#288) so the pH dynamics are declarative and characterised,
not implied.
"""

from __future__ import annotations

from dataclasses import dataclass

# van Bemmelen conversion from soil organic matter to organic carbon.
# Ref: Pribyl (2010), Geoderma 156:75-83 (the classical 1.724 factor).
OM_TO_OC_RATIO: float = 1.724

# Grams of CaCO3 that neutralise one mole of exchangeable acidity.
# CaCO3 (100.09 g/mol) neutralises 2 mol of charge, so 50 g CaCO3 per mol(H+).
# Stoichiometric; the buffer-method basis for lime requirement is
# Shoemaker, McLean & Pratt (1961), SSSAJ 25:274-277.
CACO3_G_PER_MOL_CHARGE: float = 50.0


@dataclass(frozen=True)
class LayerBufferProperties:
    """Soil properties of one layer that set its pH buffer capacity.

    Mirrors the four ``SoilLayer`` fields the lime response needs. Held on
    :class:`~agrogame.soil.chemistry.module.SoilChemistryModule` rather than
    in ``ChemistryState`` because they are fixed soil properties, not state:
    a snapshot restore replaces pH only and must not disturb them.

    Attributes:
        depth_cm: Layer thickness (cm).
        bulk_density_g_cm3: Dry bulk density (g/cm3).
        clay_pct: Clay content (% by mass).
        organic_matter_pct: Soil organic matter (% by mass).
    """

    depth_cm: float
    bulk_density_g_cm3: float
    clay_pct: float
    organic_matter_pct: float

    def __post_init__(self) -> None:
        if self.depth_cm <= 0.0:
            raise ValueError(f"depth_cm must be > 0, got {self.depth_cm}")
        if self.bulk_density_g_cm3 <= 0.0:
            raise ValueError(
                f"bulk_density_g_cm3 must be > 0, got {self.bulk_density_g_cm3}"
            )
        if not (0.0 <= self.clay_pct <= 100.0):
            raise ValueError(f"clay_pct must be in [0, 100], got {self.clay_pct}")
        if self.organic_matter_pct < 0.0:
            raise ValueError(
                f"organic_matter_pct must be >= 0, got {self.organic_matter_pct}"
            )

    @property
    def soil_mass_kg_ha(self) -> float:
        """Dry soil mass of the layer (kg/ha).

        ``depth_cm x bulk_density(g/cm3) x 1e5`` — one hectare of 1 cm depth at
        1 g/cm3 is 1e5 kg.
        """
        return self.depth_cm * self.bulk_density_g_cm3 * 1.0e5

    @property
    def organic_carbon_pct(self) -> float:
        """Organic carbon (% by mass), from organic matter via van Bemmelen."""
        return self.organic_matter_pct / OM_TO_OC_RATIO


@dataclass(frozen=True)
class ChemistryParams:
    """Coefficients governing per-layer soil pH dynamics.

    Attributes:
        base_ph: Initial per-layer pH when state is built from defaults.
        default_target_ph: Buffering target used when a ``DayTick`` carries
            no explicit ``target_ph``.
        buffering_rate: Daily fraction of the gap to ``target_ph`` that pH
            relaxes towards (weak buffering tendency).
        no3_leach_ph_delta: pH drop applied on nitrate (NO3) leaching —
            nitrate loss tends to acidify slightly.
        p_fixation_ph_delta: pH drop applied when phosphorus fixation occurs
            (a small local acidification proxy).
        phbc_clay_max_cmol_kg: Asymptotic clay contribution to pH buffer
            capacity, cmol(H+)/kg per pH unit.
        phbc_clay_half_pct: Clay content (%) at which the clay term reaches
            half of ``phbc_clay_max_cmol_kg``.
        phbc_oc_cmol_per_pct: pH buffer capacity added per % organic carbon,
            cmol(H+)/kg per pH unit.
        acidifying_ph_delta_per_kg_ha: pH drop per kg/ha of acidifying
            fertilizer applied.
        ph_floor: Lower clamp on per-layer pH.
        ph_ceiling: Upper clamp on per-layer pH.
    """

    base_ph: float = 6.8
    default_target_ph: float = 6.8
    buffering_rate: float = 0.001
    no3_leach_ph_delta: float = 0.005
    p_fixation_ph_delta: float = 0.002
    # --- pH buffer capacity (pHBC), cmol(H+)/kg soil per pH unit ----------
    # Measured pHBC of mineral soils rises with both clay and organic carbon:
    # ~1-2 cmol(H+)/kg/pH on sands, ~3-5 on loams and ~5-8 on clays.
    # Refs: Curtin & Rostad (1997), Can. J. Soil Sci. 77:621-626;
    #       Aitken & Moody (1994), Aust. J. Soil Res. 32:975-984.
    # The clay term saturates (Michaelis form) because measured pHBC rises
    # less than proportionally with clay across texture classes, while the
    # organic-carbon term stays linear. The three coefficients below are
    # *calibrated* so every shipped soil preset lands inside the published
    # band for its texture class; they are not a published regression.
    phbc_clay_max_cmol_kg: float = 8.5
    phbc_clay_half_pct: float = 25.0
    phbc_oc_cmol_per_pct: float = 0.6
    acidifying_ph_delta_per_kg_ha: float = 0.0005
    ph_floor: float = 4.0
    ph_ceiling: float = 9.0
