"""Immutable redox parameters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RedoxParams:
    """Parameters for Eh computation and greenhouse gas processes.

    Eh-WFPS sigmoid: Eh_eq = eh_max - (eh_max - eh_min) * sigmoid(k*(WFPS - midpoint))
    Ref: Simplified from Reddy & DeLaune 2008, Biogeochemistry of Wetlands.

    Attributes:
        eh_max_mv: Maximum Eh under fully aerobic conditions (mV).
        eh_min_mv: Minimum Eh under fully anaerobic conditions (mV).
        sigmoid_k: Steepness of Eh-WFPS sigmoid curve.
        sigmoid_midpoint: WFPS at which Eh is halfway between max and min.
        tau_days: Time constant for Eh exponential decay toward equilibrium.
        ch4_base_rate_kg_c_ha_day: Base CH4 production rate at Eh < -200mV.
        ch4_q10: Temperature sensitivity of CH4 production.
        ch4_ref_temp_c: Reference temperature for Q10 scaling.
        ch4_oxidation_fraction: Fraction of CH4 oxidized in aerobic surface.
        fe_p_release_fraction: Daily fraction of fixed_p released when Eh < 100 mV.
        rhizosphere_wfps_reduction: WFPS reduction per unit root fraction.
        o2_anaerobic_frac: Soil-air O2 volume fraction at and below which the
            O2-driven equilibrium Eh is ``eh_min_mv``. 0.2 %: Fe(III) and
            sulfate reduction need near-complete O2 depletion
            (Ponnamperuma 1972).
        o2_aerobic_frac: O2 fraction at and above which the O2-driven
            equilibrium Eh is ``eh_max_mv``. 5 %: the O2/H2O couple still
            buffers Eh at aerobic values (Reddy & DeLaune 2008).
    """

    eh_max_mv: float = 450.0
    eh_min_mv: float = -300.0
    sigmoid_k: float = 12.0
    sigmoid_midpoint: float = 0.75
    tau_days: float = 2.0
    ch4_base_rate_kg_c_ha_day: float = 0.15
    ch4_q10: float = 4.0
    ch4_ref_temp_c: float = 25.0
    ch4_oxidation_fraction: float = 0.6
    fe_p_release_fraction: float = 0.005
    rhizosphere_wfps_reduction: float = 0.15
    # O2-driven Eh pathway. When the caller passes o2_concentration_frac to
    # daily_step, Eh derives from the soil-air O2 fraction instead of the
    # WFPS sigmoid: eh_min_mv at and below o2_anaerobic_frac, eh_max_mv at
    # and above o2_aerobic_frac, linear in log10(O2) between them
    # (RedoxModule._equilibrium_eh_from_o2).
    o2_anaerobic_frac: float = 0.002
    o2_aerobic_frac: float = 0.05
