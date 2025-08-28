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
