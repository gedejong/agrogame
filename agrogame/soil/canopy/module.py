from __future__ import annotations

import math

from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.phenology import StageChanged, PhenologyStage

from .params import CanopyParams
from .types import CanopyState, CanopyFluxes
from .events import LightIntercepted, BiomassAccumulated, LAIUpdated


class CanopyModule:
    """Canopy growth and light interception.

    Responsibilities:
    - Compute intercepted PAR via Beer–Lambert law (k, LAI)
    - Convert intercepted PAR to biomass using RUE and stress/temperature factors
    - Update LAI from new leaf biomass with SLA and senescence, with logistic taper
    - Integrate with phenology to increase senescence during grain fill

    Units:
    - PAR: MJ m^-2 day^-1
    - Biomass: g m^-2
    - LAI: m^2 leaf per m^2 ground
    """

    def __init__(self, params: CanopyParams, event_bus: EventBus | None = None):
        self.params = params
        self.state = CanopyState(lai=0.0, biomass_g_m2=0.0)
        self.event_bus = event_bus

        if self.event_bus is not None:
            self.event_bus.subscribe(StageChanged, self._on_stage_changed)

        # Stage modifiers (simple): adjust senescence after flowering
        self._senescence_multiplier = 1.0

    def _on_stage_changed(self, event: StageChanged) -> None:
        # Bootstrap canopy at emergence
        if event.to_stage == PhenologyStage.EMERGED and self.state.lai <= 0.0:
            self.state.lai = max(self.state.lai, 0.1)
        if event.to_stage in (PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY):
            self._senescence_multiplier = 2.0
        else:
            self._senescence_multiplier = 1.0

    def calculate_light_interception(self, incident_par_mj_m2: float) -> CanopyFluxes:
        """Return intercepted PAR and emit LightIntercepted event.

        Args:
            incident_par_mj_m2: Daily incident PAR (MJ m^-2).
        """
        if self.state.lai <= 0.0 or incident_par_mj_m2 <= 0.0:
            if self.event_bus is not None:
                self.event_bus.emit(
                    LightIntercepted(
                        fraction=0.0,
                        incident_par_mj_m2=incident_par_mj_m2,
                        intercepted_par_mj_m2=0.0,
                    )
                )
            return CanopyFluxes(intercepted_par_mj_m2=0.0, biomass_increment_g_m2=0.0)

        k = self.params.extinction_coefficient_k
        fraction = 1.0 - math.exp(-k * self.state.lai)
        intercepted = incident_par_mj_m2 * fraction
        if self.event_bus is not None:
            self.event_bus.emit(
                LightIntercepted(
                    fraction=fraction,
                    incident_par_mj_m2=incident_par_mj_m2,
                    intercepted_par_mj_m2=intercepted,
                )
            )
        return CanopyFluxes(
            intercepted_par_mj_m2=intercepted, biomass_increment_g_m2=0.0
        )

    def calculate_biomass_growth(
        self,
        intercepted_par_mj_m2: float,
        temp_factor: float,
        water_stress: float,
        n_stress: float,
    ) -> float:
        """Compute biomass increment from intercepted PAR.

        biomass = PAR_intercepted * RUE * temp_factor * min(water_stress, n_stress)
        """
        stress = min(max(water_stress, 0.0), 1.0)
        stress = min(stress, max(min(n_stress, 1.0), 0.0))
        rue = self.params.radiation_use_efficiency_g_per_mj
        return intercepted_par_mj_m2 * max(0.0, temp_factor) * rue * stress

    def update_lai(self, new_leaf_biomass_g_m2: float) -> float:
        """Update LAI from new leaf biomass and senescence with logistic taper."""
        prev = self.state.lai
        growth = (
            max(0.0, new_leaf_biomass_g_m2) * self.params.specific_leaf_area_m2_per_g
        )
        # Logistic-like deceleration as LAI approaches lai_max to shape S-curve
        if self.params.lai_max > 0.0:
            growth *= max(0.0, 1.0 - (self.state.lai / self.params.lai_max))
        sen = (
            self.state.lai
            * self.params.senescence_rate_per_day
            * self._senescence_multiplier
        )
        self.state.lai = min(
            self.params.lai_max, max(0.0, self.state.lai + growth - sen)
        )
        if self.event_bus is not None and abs(self.state.lai - prev) > 1e-9:
            self.event_bus.emit(LAIUpdated(previous_lai=prev, new_lai=self.state.lai))
        return self.state.lai

    def daily_step(
        self,
        incident_par_mj_m2: float,
        temp_factor: float,
        water_stress: float,
        n_stress: float,
    ) -> CanopyFluxes:
        fx = self.calculate_light_interception(incident_par_mj_m2)
        biomass_inc = self.calculate_biomass_growth(
            fx.intercepted_par_mj_m2, temp_factor, water_stress, n_stress
        )
        self.state.biomass_g_m2 += biomass_inc
        self.update_lai(new_leaf_biomass_g_m2=biomass_inc)
        if self.event_bus is not None and biomass_inc > 0.0:
            self.event_bus.emit(
                BiomassAccumulated(
                    increment_g_m2=biomass_inc, total_g_m2=self.state.biomass_g_m2
                )
            )
        return CanopyFluxes(
            intercepted_par_mj_m2=fx.intercepted_par_mj_m2,
            biomass_increment_g_m2=biomass_inc,
        )
