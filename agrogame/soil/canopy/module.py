from __future__ import annotations

import math

from agrogame.events import EventBus
from agrogame.soil.phenology import StageChanged, PhenologyStage
from agrogame.soil.phenology.events import GddAccumulated
from agrogame.plant.stress import compute_water_stress

from .params import CanopyParams
from .types import CanopyState, CanopyFluxes
from .events import LightIntercepted, BiomassAccumulated, LAIUpdated, Harvested


class CanopyModule:
    """Canopy growth and light interception.

    Responsibilities:
    - Compute intercepted PAR via Beer-Lambert law (k, LAI)
    - Convert intercepted PAR to biomass using RUE and stress/temperature factors
    - Partition biomass into leaf and stem fractions by growth stage
    - Update LAI from leaf biomass only, with SLA and senescence
    - Smooth senescence ramp during grain fill (not a step function)

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
            self.event_bus.subscribe(Harvested, self._on_harvest)
            self.event_bus.subscribe(GddAccumulated, self._on_gdd_accumulated)

        self._current_stage: PhenologyStage = PhenologyStage.PLANTED
        self._grain_fill_start_gdd: float = 0.0
        self._current_gdd: float = 0.0

    def _on_gdd_accumulated(self, event: GddAccumulated) -> None:
        self._current_gdd = event.total_gdd

    def _on_stage_changed(self, event: StageChanged) -> None:
        self._current_stage = event.to_stage
        # Bootstrap canopy at emergence
        if event.to_stage == PhenologyStage.EMERGED and self.state.lai <= 0.0:
            self.state.lai = max(self.state.lai, self.params.initial_lai_at_emergence)
        if event.to_stage == PhenologyStage.GRAIN_FILL:
            self._grain_fill_start_gdd = event.at_gdd

    @property
    def _senescence_multiplier(self) -> float:
        """Compute senescence multiplier based on current phenological stage.

        Vegetative/emerged: reduced fraction (slow leaf turnover).
        Flowering: moderate (lower canopy leaves begin dying).
        Grain fill: smooth linear ramp from flowering level to
        senescence_grain_fill_max over the grain fill GDD duration.
        Maturity: peak senescence.
        """
        stage = self._current_stage
        if stage in (PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE):
            return self.params.senescence_vegetative_fraction
        if stage == PhenologyStage.FLOWERING:
            return self.params.senescence_flowering_fraction
        if stage == PhenologyStage.GRAIN_FILL:
            duration = self.params.grain_fill_duration_gdd
            if duration <= 0.0:
                return self.params.senescence_grain_fill_max
            progress = (self._current_gdd - self._grain_fill_start_gdd) / duration
            progress = max(0.0, min(1.0, progress))
            start = self.params.senescence_flowering_fraction
            return start + progress * (self.params.senescence_grain_fill_max - start)
        if stage == PhenologyStage.MATURITY:
            return self.params.senescence_grain_fill_max
        return 1.0

    @property
    def _leaf_fraction(self) -> float:
        """Fraction of daily biomass allocated to leaves, by growth stage."""
        stage = self._current_stage
        if stage in (
            PhenologyStage.PLANTED,
            PhenologyStage.EMERGED,
            PhenologyStage.VEGETATIVE,
        ):
            return self.params.leaf_fraction_vegetative
        if stage == PhenologyStage.FLOWERING:
            return self.params.leaf_fraction_flowering
        if stage in (PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY):
            return self.params.leaf_fraction_grain_fill
        return self.params.leaf_fraction_vegetative

    def calculate_light_interception(self, incident_par_mj_m2: float) -> CanopyFluxes:
        """Compute intercepted PAR and emit a LightIntercepted event.

        Args:
            incident_par_mj_m2: Daily incident PAR (MJ m^-2).

        Returns:
            CanopyFluxes: Intercepted PAR and a zero biomass increment placeholder.
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

    def _on_harvest(self, ev: Harvested) -> None:
        frac = max(0.0, min(1.0, float(ev.fraction_remaining)))
        prev_lai = self.state.lai
        self.state.lai *= frac
        self.state.biomass_g_m2 *= frac
        self.state.stem_biomass_g_m2 *= frac
        self.state.grain_biomass_g_m2 *= frac
        if self.event_bus is not None and abs(self.state.lai - prev_lai) > 1e-9:
            self.event_bus.emit(
                LAIUpdated(previous_lai=prev_lai, new_lai=self.state.lai)
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
        # Accumulate grain during grain fill (DSSAT-style daily HI allocation)
        if self._current_stage in (
            PhenologyStage.GRAIN_FILL,
            PhenologyStage.MATURITY,
        ):
            self.state.grain_biomass_g_m2 += biomass_inc * self.params.harvest_index
        # Partition into leaf and stem fractions
        leaf_fraction = self._leaf_fraction
        leaf_biomass = biomass_inc * leaf_fraction
        stem_biomass = biomass_inc * (1.0 - leaf_fraction)
        self.state.stem_biomass_g_m2 += stem_biomass
        self.update_lai(new_leaf_biomass_g_m2=leaf_biomass)
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

    def daily_step_with_transpiration(
        self,
        incident_par_mj_m2: float,
        temp_factor: float,
        actual_transpiration_mm: float,
        potential_transpiration_mm: float,
        n_stress: float,
    ) -> CanopyFluxes:
        """Variant that derives water stress from ET supply/demand.

        Computes water stress via compute_water_stress(actual, demand) and
        delegates to daily_step.
        """
        ws = compute_water_stress(actual_transpiration_mm, potential_transpiration_mm)
        return self.daily_step(
            incident_par_mj_m2=incident_par_mj_m2,
            temp_factor=temp_factor,
            water_stress=ws,
            n_stress=n_stress,
        )
