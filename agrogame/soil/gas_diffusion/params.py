"""Immutable gas diffusion parameters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GasDiffusionParams:
    """Parameters for soil gas (O2/CO2) diffusion.

    Steady-state Fickian diffusion with Millington-Quirk tortuosity
    (Millington & Quirk 1961) and temperature-corrected diffusivity
    (Massman 1998). Critical air-filled porosity threshold from
    Stepniewski 1994.

    Attributes:
        d_o2_air_ref_m2_per_s: Reference O2 diffusivity in air at
            T_ref_k. Ref: Massman 1998, Atmos. Environ. — ~2.0e-5 m2/s.
        d_co2_air_ref_m2_per_s: Reference CO2 diffusivity in air at
            T_ref_k. Ref: Massman 1998 — ~1.6e-5 m2/s.
        t_ref_k: Reference temperature (K). 293.15 K = 20 C.
        temp_exponent: Exponent in D(T) = D_ref * (T/T_ref)^n.
            Ref: Massman 1998 — n = 1.75 for O2/CO2 in air.
        atmospheric_o2_frac: Atmospheric O2 volume fraction (dimensionless).
            Standard value 0.2095 (Campbell & Norman 1998).
        atmospheric_co2_frac: Atmospheric CO2 volume fraction. ~420 ppm
            as of 2024; use 0.00042 (Tans & Keeling, NOAA).
        critical_air_porosity: Air-filled porosity below which the layer
            is flagged anaerobic even if O2 concentration solve returns
            a non-zero value. Ref: Stepniewski 1994 — ~0.10 m3/m3.
        anaerobic_o2_threshold_frac: O2 volume fraction below which a
            microsite is considered anaerobic. Ref: Skopp et al. 1990
            — ~0.02 (2% of atmospheric).
        respiratory_quotient: mol O2 consumed per mol CO2 produced.
            Ref: Farquhar et al. 1980 — ~1.0 for carbohydrate substrate.
        mol_volume_m3_per_mol: Molar volume of ideal gas at T_ref
            (24.0 L/mol at 20 C). Used to convert mol CO2 flux to
            volumetric flux.
    """

    d_o2_air_ref_m2_per_s: float = 2.0e-5
    d_co2_air_ref_m2_per_s: float = 1.6e-5
    t_ref_k: float = 293.15
    temp_exponent: float = 1.75
    atmospheric_o2_frac: float = 0.2095
    atmospheric_co2_frac: float = 0.00042
    critical_air_porosity: float = 0.10
    anaerobic_o2_threshold_frac: float = 0.02
    respiratory_quotient: float = 1.0
    mol_volume_m3_per_mol: float = 0.024
