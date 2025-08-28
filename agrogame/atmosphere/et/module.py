from __future__ import annotations

import math

from agrogame.soil.models import SoilProfile
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState

from .params import EtParams
from .types import EtActual, EtComponents, EtState


class Evapotranspiration:
    def __init__(self, params: EtParams | None = None) -> None:
        self.params = params or EtParams()

    def priestley_taylor(self, temp_mean_c: float, net_radiation_mj_m2: float) -> float:
        # delta slope of saturation vapor pressure curve
        delta = (
            4098.0
            * (0.6108 * math.exp(17.27 * temp_mean_c / (temp_mean_c + 237.3)))
            / (temp_mean_c + 237.3) ** 2
        )
        gamma = 0.067  # psychrometric constant (kPa/°C)
        # Convert MJ to equivalent mm via latent heat 2.45 MJ/kg (≈ mm)
        et0 = (
            self.params.pt_alpha
            * (delta / (delta + gamma))
            * net_radiation_mj_m2
            / 2.45
        )
        return max(0.0, et0)

    def _saturation_vapor_pressure_kpa(self, temp_c: float) -> float:
        return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))

    def _psychrometric_constant_kpa_per_c(self, elevation_m: float = 0.0) -> float:
        # FAO56 approx: gamma = 0.000665 * P, P(kPa) = 101.3*((293-0.0065z)/293)^5.26
        p_kpa: float = float(101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26)
        return float(0.000665 * p_kpa)

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
            4098.0
            * self._saturation_vapor_pressure_kpa(temp_mean_c)
            / (temp_mean_c + 237.3) ** 2
        )
        gamma = self._psychrometric_constant_kpa_per_c(elevation_m)
        es = self._saturation_vapor_pressure_kpa(temp_mean_c)
        ea = es * max(0.0, min(1.0, relative_humidity_pct / 100.0))
        vpd = max(0.0, es - ea)
        # Convert Rn [MJ m-2 d-1] to equivalent mm: divide by latent heat 2.45
        rn_mm = max(0.0, net_radiation_mj_m2) / 2.45

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
        numerator = delta * rn_mm + gamma * (900.0 / (temp_mean_c + 273.0)) * u2 * vpd
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

    def ritchie_evaporation(
        self, state: EtState, potential_evap_mm: float, topsoil_available_mm: float
    ) -> float:
        if potential_evap_mm <= 0.0:
            return 0.0
        taken = 0.0
        if state.cumulative_evap_mm < self.params.stage1_limit_mm:
            take1 = min(potential_evap_mm, topsoil_available_mm)
            taken += take1
            state.cumulative_evap_mm += take1
            potential_evap_mm -= take1
            topsoil_available_mm -= take1
        if potential_evap_mm > 0.0 and topsoil_available_mm > 0.0:
            t = max(0.0, state.cumulative_evap_mm - self.params.stage1_limit_mm)
            stage2 = self.params.ritchie_coef * (t + 1.0) ** -0.5
            take2 = min(stage2, potential_evap_mm, topsoil_available_mm)
            taken += take2
            state.cumulative_evap_mm += take2
        return max(0.0, taken)

    def actual_et(
        self,
        profile: SoilProfile,
        water_state: SoilWaterState,
        water_model: CascadingBucketWaterModel,
        et: EtComponents,
        root_fractions: tuple[float, ...] | list[float],
    ) -> EtActual:
        # Soil evaporation from top layer availability
        top_current = water_state.layer_storage_mm(profile, 0)
        top_wp = profile.layers[0].wilting_point * profile.layers[0].depth_cm * 10.0
        top_avail = max(0.0, top_current - top_wp)
        st = EtState()
        evap_taken = self.ritchie_evaporation(st, et.potential_evap_mm, top_avail)
        if evap_taken > 0.0:
            water_state.set_layer_storage_mm(profile, 0, top_current - evap_taken)

        # Transpiration extraction across rooted layers
        transp_supplied = water_model.extract_transpiration_by_roots(
            profile, water_state, et.potential_transp_mm, root_fractions
        )
        return EtActual(evaporation_mm=evap_taken, transpiration_mm=transp_supplied)
