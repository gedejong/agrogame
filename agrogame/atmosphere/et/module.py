from __future__ import annotations

import math

from .ports import WaterProfile, WaterState, WaterActuator

from .params import EtParams
from agrogame.weather.constants import (
    DELTA_NUMERATOR,
    FAO_PM_NUMERATOR_COEF,
    ABSOLUTE_ZERO_C,
    LATENT_HEAT_MJ_PER_KG,
    PSYCHROMETRIC_COEFF_PER_KPA,
    SEA_LEVEL_PRESSURE_KPA,
    PRESSURE_TEMP_REF_K,
    LAPSE_RATE_K_PER_M,
    PRESSURE_EXPONENT,
    FAO_SVP_A_KPA,
    FAO_SVP_B,
    FAO_SVP_C,
    PSYCHROMETRIC_CONST_APPROX_KPA_PER_C,
)
from .types import EtActual, EtComponents, EtState


class Evapotranspiration:
    def __init__(self, params: EtParams | None = None) -> None:
        self.params = params or EtParams()

    def priestley_taylor(self, temp_mean_c: float, net_radiation_mj_m2: float) -> float:
        # delta slope of saturation vapor pressure curve
        delta = (
            DELTA_NUMERATOR
            * (
                FAO_SVP_A_KPA
                * math.exp(FAO_SVP_B * temp_mean_c / (temp_mean_c + FAO_SVP_C))
            )
            / (temp_mean_c + FAO_SVP_C) ** 2
        )
        gamma = PSYCHROMETRIC_CONST_APPROX_KPA_PER_C  # kPa/°C
        # Convert MJ to equivalent mm via latent heat
        et0 = (
            self.params.pt_alpha
            * (delta / (delta + gamma))
            * net_radiation_mj_m2
            / LATENT_HEAT_MJ_PER_KG
        )
        return max(0.0, et0)

    def _saturation_vapor_pressure_kpa(self, temp_c: float) -> float:
        return FAO_SVP_A_KPA * math.exp(FAO_SVP_B * temp_c / (temp_c + FAO_SVP_C))

    def _psychrometric_constant_kpa_per_c(self, elevation_m: float = 0.0) -> float:
        # FAO-56 approx
        p_kpa: float = float(
            SEA_LEVEL_PRESSURE_KPA
            * (
                (PRESSURE_TEMP_REF_K - LAPSE_RATE_K_PER_M * elevation_m)
                / PRESSURE_TEMP_REF_K
            )
            ** PRESSURE_EXPONENT
        )
        return float(PSYCHROMETRIC_COEFF_PER_KPA * p_kpa)

    def penman_monteith(
        self,
        net_radiation_mj_m2: float,
        temp_mean_c: float,
        wind_m_s: float,
        relative_humidity_pct: float,
        elevation_m: float = 0.0,
        canopy_height_m: float | None = None,
    ) -> float:
        # FAO-56 reference crop Penman–Monteith (daily)
        delta = (
            DELTA_NUMERATOR
            * self._saturation_vapor_pressure_kpa(temp_mean_c)
            / (temp_mean_c + FAO_SVP_C) ** 2
        )
        gamma = self._psychrometric_constant_kpa_per_c(elevation_m)
        es = self._saturation_vapor_pressure_kpa(temp_mean_c)
        ea = es * max(0.0, min(1.0, relative_humidity_pct / 100.0))
        vpd = max(0.0, es - ea)
        # Convert Rn [MJ m-2 d-1] to equivalent mm: divide by latent heat 2.45
        rn_mm = max(0.0, net_radiation_mj_m2) / LATENT_HEAT_MJ_PER_KG

        # Aerodynamic resistance ra (s/m), simple FAO daily: ra = 208/(u2)
        u2 = max(0.1, wind_m_s)  # avoid zero
        ra = 208.0 / u2

        # Surface (stomatal) resistance rs (s/m)
        # Canopy height available for future resistance scaling if needed
        # (not currently used)
        vpd_factor = max(
            0.2,
            1.0 - self.params.vpd_sensitivity * max(0.0, vpd - self.params.vpd_ref_kpa),
        )
        rs = self.params.rs_min_s_m / vpd_factor

        # FAO-56 PM daily in mm/day using rn_mm, vpd, ra, rs
        # Note: aerodynamic term must be scaled by psychrometric constant (gamma)
        numerator = (
            delta * rn_mm
            + gamma
            * (FAO_PM_NUMERATOR_COEF / (temp_mean_c + ABSOLUTE_ZERO_C))
            * u2
            * vpd
        )
        denominator = delta + gamma * (1.0 + rs / ra)
        et0 = numerator / max(1e-6, denominator)
        return max(0.0, et0)

    def potential_components(self, et0_mm: float, lai: float) -> EtComponents:
        k = self.params.extinction_coefficient_k
        canopy_cover = 1.0 - math.exp(-max(0.0, k) * max(0.0, lai))
        potential_transp = et0_mm * canopy_cover
        potential_evap = et0_mm - potential_transp
        return EtComponents(
            potential_evap_mm=max(0.0, potential_evap),
            potential_transp_mm=max(0.0, potential_transp),
            et0_mm=max(0.0, et0_mm),
        )

    def potential_components_with_vpd(
        self, et0_mm: float, lai: float, vpd_kpa: float
    ) -> EtComponents:
        """Partition ET0 into potential E/T with stomatal VPD response.

        Scales potential transpiration by a stomatal factor that decreases with
        VPD above the reference (linear clamp to [0.2, 1.0]). Evaporation gets
        the remaining share of ET0.
        """
        k = self.params.extinction_coefficient_k
        canopy_cover = 1.0 - math.exp(-max(0.0, k) * max(0.0, lai))
        # Stomatal VPD factor analogous to Penman–Monteith rs scaling
        vpd_excess = max(0.0, vpd_kpa - self.params.vpd_ref_kpa)
        stomatal_factor = max(0.2, 1.0 - self.params.vpd_sensitivity * vpd_excess)
        base_transp = et0_mm * canopy_cover
        potential_transp = max(0.0, base_transp * stomatal_factor)
        potential_evap = max(0.0, et0_mm - potential_transp)
        return EtComponents(
            potential_evap_mm=potential_evap,
            potential_transp_mm=potential_transp,
            et0_mm=max(0.0, et0_mm),
        )

    def et0(
        self,
        temp_mean_c: float,
        net_radiation_mj_m2: float,
        *,
        method: str | None = None,
        wind_m_s: float = 2.0,
        relative_humidity_pct: float = 50.0,
        elevation_m: float = 0.0,
        canopy_height_m: float | None = None,
    ) -> float:
        m = (method or self.params.method).lower()
        if m.startswith("priestley"):
            return self.priestley_taylor(temp_mean_c, net_radiation_mj_m2)
        if m.startswith("penman"):
            return self.penman_monteith(
                net_radiation_mj_m2=net_radiation_mj_m2,
                temp_mean_c=temp_mean_c,
                wind_m_s=wind_m_s,
                relative_humidity_pct=relative_humidity_pct,
                elevation_m=elevation_m,
                canopy_height_m=canopy_height_m,
            )
        # default
        return self.priestley_taylor(temp_mean_c, net_radiation_mj_m2)

    @staticmethod
    def residue_adjusted_params(
        stage1_limit_mm: float,
        ritchie_coef: float,
        cover_fraction: float,
        stage1_reduction: float = 0.6,
        stage2_reduction: float = 0.4,
    ) -> tuple[float, float]:
        """Return (adjusted_stage1, adjusted_coef) given residue cover fraction."""
        frac = max(0.0, min(1.0, cover_fraction))
        adj_stage1 = stage1_limit_mm * (1.0 - stage1_reduction * frac)
        adj_coef = ritchie_coef * (1.0 - stage2_reduction * frac)
        return max(0.0, adj_stage1), max(0.0, adj_coef)

    def ritchie_evaporation(
        self,
        state: EtState,
        potential_evap_mm: float,
        topsoil_available_mm: float,
        *,
        stage1_limit_mm: float | None = None,
        ritchie_coef: float | None = None,
    ) -> float:
        if potential_evap_mm <= 0.0:
            return 0.0
        s1_limit = (
            stage1_limit_mm
            if stage1_limit_mm is not None
            else self.params.stage1_limit_mm
        )
        coef = ritchie_coef if ritchie_coef is not None else self.params.ritchie_coef
        taken = 0.0
        if state.cumulative_evap_mm < s1_limit:
            take1 = min(potential_evap_mm, topsoil_available_mm)
            taken += take1
            state.cumulative_evap_mm += take1
            potential_evap_mm -= take1
            topsoil_available_mm -= take1
        if potential_evap_mm > 0.0 and topsoil_available_mm > 0.0:
            t = max(0.0, state.cumulative_evap_mm - s1_limit)
            stage2 = coef * (t + 1.0) ** -0.5
            take2 = min(stage2, potential_evap_mm, topsoil_available_mm)
            taken += take2
            state.cumulative_evap_mm += take2
        return max(0.0, taken)

    def actual_et(
        self,
        profile: WaterProfile,
        water_state: WaterState,
        water_model: WaterActuator,
        et: EtComponents,
        root_fractions: tuple[float, ...] | list[float],
        *,
        evap_state: EtState | None = None,
        residue_cover_fraction: float = 0.0,
    ) -> EtActual:
        # Soil evaporation from top layer availability
        top_current = water_state.layer_storage_mm(profile, 0)
        top_wp = profile.layers[0].wilting_point * profile.layers[0].depth_cm * 10.0
        top_avail = max(0.0, top_current - top_wp)
        st = evap_state if evap_state is not None else EtState()
        # Compute residue-adjusted Ritchie parameters
        adj_s1, adj_coef = self.residue_adjusted_params(
            self.params.stage1_limit_mm,
            self.params.ritchie_coef,
            residue_cover_fraction,
            self.params.residue_stage1_reduction,
            self.params.residue_stage2_reduction,
        )
        evap_taken = self.ritchie_evaporation(
            st,
            et.potential_evap_mm,
            top_avail,
            stage1_limit_mm=adj_s1,
            ritchie_coef=adj_coef,
        )
        if evap_taken > 0.0:
            _ = water_model.apply_evaporation(profile, water_state, evap_taken)

        # Transpiration extraction across rooted layers (clamped to potential)
        transp_supplied = water_model.extract_transpiration_by_roots(
            profile, water_state, et.potential_transp_mm, root_fractions
        )
        transp_supplied = min(transp_supplied, et.potential_transp_mm)
        return EtActual(evaporation_mm=evap_taken, transpiration_mm=transp_supplied)
