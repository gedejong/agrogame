from __future__ import annotations

import math

from agrogame.events import EventBus
from agrogame.soil.phenology import StageChanged, PhenologyStage
from agrogame.soil.phenology.events import GddAccumulated
from agrogame.plant.stress import compute_water_stress

from .params import CanopyParams
from .types import CanopyState, CanopyFluxes
from .events import (
    LightIntercepted,
    BiomassAccumulated,
    LAIUpdated,
    Harvested,
    GrainNumberSet,
)


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
        # Sink-source grain model (#321): biomass at anthesis and a freeze
        # flag for the peri-anthesis grain-number window.
        self._lag_start_biomass: float = 0.0
        self._grain_number_frozen: bool = False

    def _on_gdd_accumulated(self, event: GddAccumulated) -> None:
        self._current_gdd = event.total_gdd

    def _on_stage_changed(self, event: StageChanged) -> None:
        self._current_stage = event.to_stage
        # Bootstrap canopy at emergence
        if event.to_stage == PhenologyStage.EMERGED and self.state.lai <= 0.0:
            self.state.lai = max(self.state.lai, self.params.initial_lai_at_emergence)
        if event.to_stage == PhenologyStage.GRAIN_FILL:
            self._grain_fill_start_gdd = event.at_gdd
            # Anchor the peri-anthesis grain-number window (#321): grain
            # number will be set from biomass accrued past this point.
            self._lag_start_biomass = self.state.biomass_g_m2
            self._grain_number_frozen = False
            self.state.grain_number = 0.0

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
        self.state.grain_number *= frac  # reset grain number for next cycle (#321)
        self._lag_start_biomass *= frac
        self._grain_number_frozen = False
        self.state.last_water_stress = 1.0  # Reset to no-stress after harvest
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

    def _update_grain_number(self) -> None:
        """Set (then freeze) potential grain number over the critical window.

        Grain number is proportional to assimilate accrued during the
        post-anthesis lag/critical window (Andrade et al. 1999 for maize;
        Fischer 1985 for wheat; DSSAT CERES G1 coefficient analogue). Cold,
        water and N stress all lower it via the reduced source growth. Once
        the window (``grain_set_window_gdd``) closes the number is frozen, so
        later filling changes kernel weight, never grain number.
        """
        p = self.params
        window_end = self._grain_fill_start_gdd + p.grain_set_window_gdd
        if self._current_gdd <= window_end:
            lag_growth = self.state.biomass_g_m2 - self._lag_start_biomass
            self.state.grain_number = p.grains_per_g_source * max(0.0, lag_growth)
        elif not self._grain_number_frozen:
            self._grain_number_frozen = True
            if self.event_bus is not None:
                self.event_bus.emit(
                    GrainNumberSet(
                        grain_number=self.state.grain_number,
                        window_source_g_m2=self.state.grain_number
                        / p.grains_per_g_source,
                        at_gdd=self._current_gdd,
                    )
                )

    def _partition_grain(
        self, biomass_inc: float, leaf_fraction: float, heat_grain_factor: float
    ) -> None:
        """Partition the day's non-leaf increment (and reserves) into grain/stem.

        Sink-source model (``grains_per_g_source > 0``): a daily fill *demand*
        (single-kernel rate x grain number, slowed by post-anthesis heat and
        bounded by the remaining total sink = number x potential kernel
        weight) is met from current assimilate first, then from remobilised
        reserves. Grain number thus sets total yield, the fill rate governs
        kernel weight, and stress on either lowers grain (CERES-style; Andrade
        et al. 1999; Fischer 1985). Falls back to the legacy fixed-HI split
        for non-grain / un-migrated presets. Mutates grain and stem in place.
        """
        p = self.params
        nonleaf = biomass_inc * (1.0 - leaf_fraction)
        in_grain_fill = self._current_stage == PhenologyStage.GRAIN_FILL
        if p.grains_per_g_source <= 0.0:
            self._partition_grain_legacy(biomass_inc, nonleaf, heat_grain_factor)
            return
        if not in_grain_fill:
            self.state.stem_biomass_g_m2 += nonleaf
            return
        self._update_grain_number()
        total_sink = self.state.grain_number * p.potential_kernel_weight_mg * 1e-3
        remaining_total = max(0.0, total_sink - self.state.grain_biomass_g_m2)
        # Potential fill demand today = single-kernel rate x number (CERES G2),
        # slowed by post-anthesis heat stress, never beyond the remaining sink.
        demand = min(
            self.state.grain_number
            * p.kernel_fill_rate_mg_per_grain_day
            * 1e-3
            * heat_grain_factor,
            remaining_total,
        )
        # Meet demand from current assimilate first; surplus source -> stem.
        from_source = min(nonleaf, demand)
        self.state.stem_biomass_g_m2 += nonleaf - from_source
        deficit = demand - from_source
        remob = self._draw_reserves(deficit) if deficit > 0.0 else 0.0
        self.state.grain_biomass_g_m2 += from_source + remob

    def _partition_grain_legacy(
        self, biomass_inc: float, nonleaf: float, heat_grain_factor: float
    ) -> None:
        """Legacy fixed harvest-index allocation (grains_per_g_source == 0).

        Preserved verbatim so non-grain (grape HI=0) and un-migrated presets
        behave exactly as before this feature.
        """
        p = self.params
        in_grain_fill = self._current_stage == PhenologyStage.GRAIN_FILL
        grain_inc = (
            biomass_inc * p.harvest_index * heat_grain_factor if in_grain_fill else 0.0
        )
        stem = nonleaf - grain_inc
        if stem < 0.0:  # keep stem >= 0 when HI > (1 - leaf_fraction)
            grain_inc += stem
            stem = 0.0
        self.state.grain_biomass_g_m2 += grain_inc
        self.state.stem_biomass_g_m2 += stem
        if (
            in_grain_fill
            and p.remobilization_fraction > 0.0
            and self.state.stem_biomass_g_m2 > 0.0
        ):
            remob = self.state.stem_biomass_g_m2 * p.remobilization_fraction
            self.state.stem_biomass_g_m2 -= remob
            self.state.grain_biomass_g_m2 += remob

    def _draw_reserves(self, deficit: float) -> float:
        """Remobilise stem then senescing-leaf reserves to meet grain demand.

        Gebbing & Schnyder 1999: 30-50% of grain carbon comes from
        pre-anthesis reserves (stem) plus remobilised flag-leaf/canopy protein
        as leaves senesce. Internal transfer (total biomass unchanged); drawn
        only up to the day's unmet demand. Returns the mass moved to grain.
        """
        p = self.params
        drawn = 0.0
        if p.remobilization_fraction > 0.0 and self.state.stem_biomass_g_m2 > 0.0:
            take = min(
                self.state.stem_biomass_g_m2 * p.remobilization_fraction, deficit
            )
            if take > 0.0:
                self.state.stem_biomass_g_m2 -= take
                drawn += take
        if p.leaf_remob_fraction > 0.0 and drawn < deficit:
            # Implied leaf pool = total - stem - grain; moving it to grain
            # reduces the implied leaf automatically (mass conserved).
            leaf = (
                self.state.biomass_g_m2
                - self.state.stem_biomass_g_m2
                - self.state.grain_biomass_g_m2
            )
            if leaf > 0.0:
                take = min(leaf * p.leaf_remob_fraction, deficit - drawn)
                if take > 0.0:
                    drawn += take
        return drawn

    def _apply_harvest_index_cap(self) -> None:
        """Bound cumulative grain to ``hi_max`` x total biomass (#321).

        Safety ceiling that prevents runaway grain under low-stress / high-N
        conditions; the surplus is returned to stem so total biomass is
        conserved. Active only for the sink-source model.
        """
        p = self.params
        if p.grains_per_g_source <= 0.0 or p.hi_max <= 0.0:
            return
        max_grain = p.hi_max * self.state.biomass_g_m2
        excess = self.state.grain_biomass_g_m2 - max_grain
        if excess > 0.0:
            self.state.grain_biomass_g_m2 = max_grain
            self.state.stem_biomass_g_m2 += excess

    def daily_step(
        self,
        incident_par_mj_m2: float,
        temp_factor: float,
        water_stress: float,
        n_stress: float,
        heat_grain_factor: float = 1.0,
    ) -> CanopyFluxes:
        self.state.last_water_stress = water_stress
        fx = self.calculate_light_interception(incident_par_mj_m2)
        biomass_inc = self.calculate_biomass_growth(
            fx.intercepted_par_mj_m2, temp_factor, water_stress, n_stress
        )
        self.state.biomass_g_m2 += biomass_inc
        # Partition into leaf, stem, and grain so sub-pools sum to total.
        # Grain only accumulates during GRAIN_FILL (stops at maturity,
        # matching DSSAT/APSIM physiological maturity convention).
        leaf_fraction = self._leaf_fraction
        leaf_biomass = biomass_inc * leaf_fraction
        self._partition_grain(biomass_inc, leaf_fraction, heat_grain_factor)
        self._apply_harvest_index_cap()
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
        heat_grain_factor: float = 1.0,
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
            heat_grain_factor=heat_grain_factor,
        )
