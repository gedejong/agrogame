from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .biomass import MicrobialBiomassModule
from .events import (
    EnzymeGroupTotals,
    MicrobialSnapshot,
    SubstrateAvailable,
    RhizospherePrimingPulse,
    EnzymeProduced,
)
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.models import SoilProfile
from agrogame.soil.chemistry.module import SoilChemistryModule
from agrogame.plant.roots.events import RootDistributionUpdated


@dataclass
class MicrobesRuntime:
    """Wire MicrobialBiomassModule to the EventBus (DayTick + SOM/N events)."""

    event_bus: EventBus
    microbes: MicrobialBiomassModule
    profile: SoilProfile | None = None
    water_state: SoilWaterState | None = None
    chemistry: SoilChemistryModule | None = None
    # Transient daily aggregation for enzyme costs
    _daily_enzyme_totals: dict[str, float] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        # Cache latest root fractions to drive priming/exudates
        self._root_fractions: list[float] | None = None
        self._root_fractions_smoothed: list[float] | None = None
        self.event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)
        # Subscribe to enzyme production events for daily aggregation
        self.event_bus.subscribe(EnzymeProduced, self._on_enzyme_produced)

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
        if ev.phase != "nutrients":
            return
        # reset daily totals at the start of nutrients phase
        self._daily_enzyme_totals = {}
        temperature = self._compute_temperature(ev)
        wfps_by_layer = self._compute_wfps_by_layer()
        ph_by_layer = self._compute_ph_by_layer(ev)
        root_fracs = self._smooth_root_fracs()
        self._emit_substrate_and_priming(ev, root_fracs)
        self._run_microbes_step(temperature, wfps_by_layer, ph_by_layer)
        self._emit_snapshot_and_totals()

    # --- Helpers kept small to satisfy complexity gates -----------------
    def _compute_temperature(self, ev: DayTick) -> float:
        if ev.tmax_c is not None and ev.tmin_c is not None:
            return (float(ev.tmax_c) + float(ev.tmin_c)) / 2.0
        return 18.0

    def _compute_wfps_by_layer(self) -> list[float]:
        if self.profile is None or self.water_state is None:
            return [0.6] * len(self.microbes.state.layers)
        vals: list[float] = []
        for i, layer in enumerate(self.profile.layers):
            theta = self.water_state.theta[i]
            porosity = max(1e-6, layer.saturation)
            vals.append(max(0.0, min(1.0, theta / porosity)))
        return vals

    def _compute_ph_by_layer(self, ev: DayTick) -> list[float]:
        if self.chemistry is not None:
            return list(self.chemistry.ph_by_layer)
        base_ph = float(ev.target_ph) if ev.target_ph is not None else 6.8
        return [base_ph] * len(self.microbes.state.layers)

    def _smooth_root_fracs(self) -> list[float]:
        raw = self._root_fractions or [0.0] * len(self.microbes.state.layers)
        if self._root_fractions_smoothed is None:
            self._root_fractions_smoothed = list(raw)
            return self._root_fractions_smoothed
        alpha = 0.25
        n = len(self._root_fractions_smoothed)
        if len(raw) < n:
            raw = list(raw) + [0.0] * (n - len(raw))
        for i in range(min(len(raw), n)):
            prev = self._root_fractions_smoothed[i]
            cur = raw[i]
            self._root_fractions_smoothed[i] = prev + alpha * (cur - prev)
        return self._root_fractions_smoothed or raw

    def _emit_substrate_and_priming(self, ev: DayTick, root_fracs: list[float]) -> None:
        try:
            par = float(ev.par_mj_m2) if ev.par_mj_m2 is not None else 10.0
        except Exception:
            par = 10.0
        base = 2.0 * (0.6 + 0.04 * max(0.0, min(20.0, par)))
        for i in range(len(self.microbes.state.layers)):
            rf = root_fracs[i] if i < len(root_fracs) else 0.0
            available = base * (0.2 + 0.8 * rf)
            quality = 0.6 + 0.3 * rf
            self.event_bus.emit(
                SubstrateAvailable(
                    layer=i, available_c_kg_ha=available, quality_index=quality
                )
            )
            priming = 1.0 + 1.0 * rf
            if priming > 1.0:
                self.event_bus.emit(
                    RhizospherePrimingPulse(layer=i, multiplier=priming)
                )

    def _run_microbes_step(
        self, temperature: float, wfps_by_layer: list[float], ph_by_layer: list[float]
    ) -> None:
        self.microbes.daily_step_layers(
            temperature_c=temperature,
            wfps_by_layer=wfps_by_layer,
            ph_by_layer=ph_by_layer,
        )

    def _on_enzyme_produced(self, ev: EnzymeProduced) -> None:
        grp = ev.enzyme_group
        self._daily_enzyme_totals[grp] = self._daily_enzyme_totals.get(
            grp, 0.0
        ) + float(ev.production_cost_c_kg_ha)

    def _emit_snapshot_and_totals(self) -> None:
        total_c = sum(layer.c_kg_ha for layer in self.microbes.state.layers)
        total_n = sum(layer.n_kg_ha for layer in self.microbes.state.layers)
        self.event_bus.emit(
            MicrobialSnapshot(total_c_kg_ha=total_c, total_n_kg_ha=total_n)
        )
        if getattr(self, "_daily_enzyme_totals", None):
            self.event_bus.emit(
                EnzymeGroupTotals(
                    totals_c_kg_ha_by_group=dict(self._daily_enzyme_totals)
                )
            )
