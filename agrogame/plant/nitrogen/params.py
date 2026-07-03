from __future__ import annotations

from dataclasses import dataclass

# --- Critical-N dilution coefficients (whole-shoot) -------------------------
# The critical-N dilution curve is ``N_crit% = a * W^-b`` with W the shoot
# dry matter in t/ha and N_crit% the shoot N concentration (% of DM) below
# which growth is N-limited. Coefficients are crop-specific:
#
#   maize   N_crit% = 3.40 * W^-0.37   Plénet & Lemaire (2000), Plant & Soil
#                                      216:65-82 (orig. Plénet & Lemaire 1999)
#   wheat   N_crit% = 5.35 * W^-0.442  Justes et al. (1994), Ann. Bot. 74:397-407
#
# Documented fallback for crops without a fitted curve: the generic C3
# dilution of Greenwood et al. (1990), Ann. Bot. 66:425-436,
# ``N_crit% = 5.70 * W^-0.50`` (their C3 coefficient; a conservative,
# widely-cited default that sits between the maize and wheat curves).
_FALLBACK_A = 5.70  # Greenwood et al. 1990, generic C3
_FALLBACK_B = 0.50  # Greenwood et al. 1990, generic C3


@dataclass(frozen=True)
class PlantNitrogenParams:
    """Frozen parameters for the whole-shoot critical-N dilution model.

    Attributes:
        n_crit_a: Coefficient ``a`` of ``N_crit% = a * W^-b`` (% at 1 t/ha).
        n_crit_b: Dilution exponent ``b`` (dimensionless, > 0).
        reference_biomass_t_ha: Shoot DM below which the dilution curve is
            held flat at its 1 t/ha value. The power law diverges as
            W -> 0, so it is only valid above a critical biomass (~1 t/ha
            in the source fits); below it N_crit% is capped at ``a``.
        nni_stress_min: NNI at or below which the stress mapping returns
            ``stress_floor``. Anchors the low end of the linear NNI->stress
            rescale (CERES-Maize NFAC style; Jones et al. 2003).
        nni_stress_ref: NNI at or above which stress saturates at 1.0
            (luxury uptake, NNI > 1, is capped — no growth bonus).
        stress_floor: Minimum stress factor returned for severe deficiency
            (keeps a starved crop from hard-zeroing RUE in one step).
    """

    n_crit_a: float = _FALLBACK_A
    n_crit_b: float = _FALLBACK_B
    reference_biomass_t_ha: float = 1.0
    nni_stress_min: float = 0.0
    nni_stress_ref: float = 1.0
    stress_floor: float = 0.05

    def __post_init__(self) -> None:
        if self.n_crit_a <= 0.0:
            raise ValueError(f"n_crit_a must be > 0, got {self.n_crit_a}")
        if self.n_crit_b <= 0.0:
            raise ValueError(f"n_crit_b must be > 0, got {self.n_crit_b}")
        if self.reference_biomass_t_ha <= 0.0:
            raise ValueError(
                f"reference_biomass_t_ha must be > 0, got "
                f"{self.reference_biomass_t_ha}"
            )
        if not (self.nni_stress_min < self.nni_stress_ref):
            raise ValueError(
                "nni_stress_min must be < nni_stress_ref "
                f"({self.nni_stress_min} !< {self.nni_stress_ref})"
            )
