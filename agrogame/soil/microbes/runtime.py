from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .biomass import MicrobialBiomassModule
from .events import (
    EnzymeGroupTotals,
    MicrobialSnapshot,
    SubstrateAvailable,
    RhizospherePrimingPulse,
)
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.models import SoilProfile
from agrogame.soil.chemistry.module import SoilChemistryModule
from agrogame.plant.roots.events import RootDistributionUpdated


@dataclass
class MicrobesRuntime:
    event_bus: EventBus
    microbes: MicrobialBiomassModule
    profile: SoilProfile | None = None
    water_state: SoilWaterState | None = None
    chemistry: SoilChemistryModule | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        # Cache latest root fractions to drive priming/exudates
        self._root_fractions: list[float] | None = None
        self.event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)

    def _on_root_distribution(self, ev: RootDistributionUpdated) -> None:
        fracs = [max(0.0, f) for f in ev.fractions]
        s = sum(fracs) or 1.0
        fracs = [f / s for f in fracs]
        # Trim or pad to number of microbe layers if profile present
        n = len(self.microbes.state.layers)
        if len(fracs) >= n:
            self._root_fractions = fracs[:n]
        else:
            self._root_fractions = fracs + [0.0] * (n - len(fracs))

    def _on_day_tick(self, ev: DayTick) -> None:
        # Run microbes during nutrients phase so it aligns with N/P
        if ev.phase != "nutrients":
            return
        temperature = 18.0
        if ev.tmax_c is not None and ev.tmin_c is not None:
            temperature = (float(ev.tmax_c) + float(ev.tmin_c)) / 2.0
        # Compute per-layer WFPS if water_state and profile are available
        if self.profile is not None and self.water_state is not None:
            wfps_by_layer = []
            for i, layer in enumerate(self.profile.layers):
                theta = self.water_state.theta[i]
                porosity = max(1e-6, layer.saturation)
                wfps_by_layer.append(max(0.0, min(1.0, theta / porosity)))
        else:
            wfps_by_layer = [0.6] * len(self.microbes.state.layers)

        # Per-layer pH from chemistry if available; otherwise uniform
        if self.chemistry is not None:
            ph_by_layer = list(self.chemistry.ph_by_layer)
        else:
            base_ph = float(ev.target_ph) if ev.target_ph is not None else 6.8
            ph_by_layer = [base_ph] * len(self.microbes.state.layers)

        # Provide SOM/exudate substrate placeholder informed by roots
        # (to be replaced by AGRO-71)
        try:
            par = float(ev.par_mj_m2) if ev.par_mj_m2 is not None else 10.0
        except Exception:
            par = 10.0
        root_fracs = (
            self._root_fractions
            if self._root_fractions is not None
            else [0.0] * len(self.microbes.state.layers)
        )
        for i in range(len(self.microbes.state.layers)):
            rf = root_fracs[i] if i < len(root_fracs) else 0.0
            # Base substrate scales with PAR; allocate by root presence
            base = 2.0 * (0.6 + 0.04 * max(0.0, min(20.0, par)))  # 2..4.0
            available = base * (0.2 + 0.8 * rf)
            quality = 0.6 + 0.3 * rf  # better quality near roots
            self.event_bus.emit(
                SubstrateAvailable(
                    layer=i, available_c_kg_ha=available, quality_index=quality
                )
            )
            # Rhizosphere priming pulse scales with root fraction
            priming = 1.0 + 1.0 * rf
            if priming > 1.0:
                self.event_bus.emit(
                    RhizospherePrimingPulse(layer=i, multiplier=priming)
                )

        # Aggregate enzyme production by group during microbes step
        self._daily_enzyme_totals: dict[str, float] = {}
        original_emit = self.event_bus.emit

        def _emit_wrapped(event: object) -> None:
            try:
                from .events import EnzymeProduced  # local import

                if isinstance(event, EnzymeProduced):
                    grp = event.enzyme_group
                    self._daily_enzyme_totals[grp] = self._daily_enzyme_totals.get(
                        grp, 0.0
                    ) + float(event.production_cost_c_kg_ha)
            except Exception:
                pass
            original_emit(event)

        # Temporarily wrap emit
        self.event_bus.emit = _emit_wrapped  # type: ignore[method-assign]
        try:
            self.microbes.daily_step_layers(
                temperature_c=temperature,
                wfps_by_layer=wfps_by_layer,
                ph_by_layer=ph_by_layer,
            )
        finally:
            self.event_bus.emit = original_emit  # type: ignore[method-assign]
        # Emit snapshot for visualization
        total_c = sum(layer.c_kg_ha for layer in self.microbes.state.layers)
        total_n = sum(layer.n_kg_ha for layer in self.microbes.state.layers)
        self.event_bus.emit(
            MicrobialSnapshot(total_c_kg_ha=total_c, total_n_kg_ha=total_n)
        )
        if self._daily_enzyme_totals:
            self.event_bus.emit(
                EnzymeGroupTotals(
                    totals_c_kg_ha_by_group=dict(self._daily_enzyme_totals)
                )
            )
