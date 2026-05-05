from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from agrogame.events import EventBus
from .events import (
    EnzymeProduced,
    MicrobialActivityComputed,
    MicrobialFBUpdated,
    MicrobialGrowth,
    MicrobialMortality,
    SubstrateAvailable,
    RhizospherePrimingPulse,
)
from .responses import EnvironmentalResponses


@dataclass
class MicrobialParams:
    """Microbial biomass parameters: turnover, C:N ratio, enzyme economics."""

    n_layers: int
    cn_ratio: float = 8.0
    bacteria_turnover_days: float = 30.0
    fungi_turnover_days: float = 120.0
    enzyme_cost_fraction: float = 0.1  # fraction of C uptake
    # Optional relative weights for enzyme groups; default is set at runtime
    enzyme_group_weights: Dict[str, float] | None = None
    # Daily adjustment rate for fungal:bacterial ratio (0 = static)
    fb_adjust_rate: float = 0.05


@dataclass
class MicrobialLayerState:
    """Per-layer microbial pool: C, N, fungal:bacterial fraction."""

    c_kg_ha: float = 200.0
    n_kg_ha: float = 25.0
    fungal_fraction: float = 0.4  # remainder bacterial


@dataclass
class MicrobialState:
    """Whole-profile microbial state: list of per-layer pools."""

    layers: List[MicrobialLayerState]


class MicrobialBiomassModule:
    """Pure-logic microbial biomass: growth, turnover, fungal:bacterial dynamics."""

    def __init__(self, params: MicrobialParams, event_bus: EventBus) -> None:
        self.params = params
        self.event_bus = event_bus
        self.responses = EnvironmentalResponses()
        self.state = MicrobialState(
            layers=[MicrobialLayerState() for _ in range(params.n_layers)]
        )
        # Transient inputs each day
        self._substrate_today: Dict[int, tuple[float, float]] = {}
        self._priming_multiplier: Dict[int, float] = {}
        # Subscribe to substrate and priming events (optional providers)
        event_bus.subscribe(SubstrateAvailable, self._on_substrate)
        event_bus.subscribe(RhizospherePrimingPulse, self._on_priming)

    def _on_substrate(self, ev: SubstrateAvailable) -> None:
        self._substrate_today[ev.layer] = (
            float(ev.available_c_kg_ha),
            float(ev.quality_index),
        )

    def _on_priming(self, ev: RhizospherePrimingPulse) -> None:
        self._priming_multiplier[ev.layer] = max(0.0, float(ev.multiplier))

    def daily_step(self, temperature_c: float, wfps: float, ph: float) -> None:
        """Backward-compatible single-value daily step across all layers."""
        wfps_by_layer = [wfps] * len(self.state.layers)
        ph_by_layer = [ph] * len(self.state.layers)
        self.daily_step_layers(
            temperature_c=temperature_c,
            wfps_by_layer=wfps_by_layer,
            ph_by_layer=ph_by_layer,
        )

    def _normalize_enzyme_weights(self) -> Dict[str, float]:
        group_weights: Dict[str, float] = self.params.enzyme_group_weights or {
            "cellulase": 0.35,
            "protease": 0.25,
            "phosphatase": 0.25,
            "urease": 0.15,
        }
        weight_sum = sum(v for v in group_weights.values() if v > 0.0) or 1.0
        return {k: max(0.0, v) / weight_sum for k, v in group_weights.items()}

    def _compute_layer_activity(
        self, idx: int, w: float, p: float, temperature_c: float
    ) -> float:
        temp_mod = self.responses.temperature_modifier(temperature_c)
        moist_mod = self.responses.moisture_modifier(max(0.0, min(1.0, w)))
        ph_mod = self.responses.ph_modifier(p)
        base_activity = max(0.0, temp_mod * moist_mod * ph_mod)
        priming = self._priming_multiplier.get(idx, 1.0)
        return base_activity * max(0.5, min(3.0, priming))

    def _adjust_fb_ratio(
        self, idx: int, layer: MicrobialLayerState, w: float, p: float
    ) -> None:
        if self.params.fb_adjust_rate <= 0.0:
            return
        target_fungal = 0.4
        target_fungal += 0.25 * (0.6 - max(0.0, min(1.0, w)))
        target_fungal += 0.15 * ((6.5 - p) / 2.0)
        target_fungal = max(0.1, min(0.9, target_fungal))
        layer.fungal_fraction += self.params.fb_adjust_rate * (
            target_fungal - layer.fungal_fraction
        )
        layer.fungal_fraction = max(0.05, min(0.95, layer.fungal_fraction))
        self.event_bus.emit(
            MicrobialFBUpdated(layer=idx, fungal_fraction=layer.fungal_fraction)
        )

    def _apply_mortality(
        self, idx: int, layer: MicrobialLayerState, activity: float
    ) -> None:
        bacterial_fraction = 1.0 - layer.fungal_fraction
        bacteria_decay = min(1.0, 1.0 / max(1e-6, self.params.bacteria_turnover_days))
        fungi_decay = min(1.0, 1.0 / max(1e-6, self.params.fungi_turnover_days))
        daily_mortality_c = activity * (
            layer.c_kg_ha
            * (
                bacterial_fraction * bacteria_decay
                + layer.fungal_fraction * fungi_decay
            )
        )
        if daily_mortality_c <= 0.0:
            return
        n_mort = daily_mortality_c / max(1e-6, self.params.cn_ratio)
        layer.c_kg_ha -= daily_mortality_c
        layer.n_kg_ha -= n_mort
        self.event_bus.emit(
            MicrobialMortality(
                layer=idx, c_to_som_kg_ha=daily_mortality_c, n_to_som_kg_ha=n_mort
            )
        )

    def _apply_growth_and_enzymes(
        self,
        idx: int,
        layer: MicrobialLayerState,
        activity: float,
        w: float,
        p: float,
        temperature_c: float,
        norm_weights: Dict[str, float],
    ) -> None:
        available_c, quality = self._substrate_today.get(idx, (2.0, 0.8))
        km = 1.0
        vmax = 5.0
        monod = available_c / (km + max(1e-6, available_c))
        pathway_eff = (0.9 + 0.2 * layer.fungal_fraction) * (
            0.7 + 0.3 * max(0.0, min(1.0, quality))
        )
        potential_growth_c = activity * vmax * monod * pathway_eff
        enzyme_cost = potential_growth_c * self.params.enzyme_cost_fraction
        net_growth_c = max(0.0, potential_growth_c - enzyme_cost)
        if net_growth_c > 0.0:
            n_req = net_growth_c / max(1e-6, self.params.cn_ratio)
            layer.c_kg_ha += net_growth_c
            layer.n_kg_ha += n_req
            self.event_bus.emit(
                MicrobialGrowth(
                    layer=idx, delta_c_kg_ha=net_growth_c, delta_n_kg_ha=n_req
                )
            )
        if enzyme_cost > 0.0:
            for group, wgt in norm_weights.items():
                group_cost = enzyme_cost * wgt
                if group_cost <= 0.0:
                    continue
                self.event_bus.emit(
                    EnzymeProduced(
                        layer=idx,
                        enzyme_group=group,
                        production_cost_c_kg_ha=group_cost,
                        params={
                            "activity": activity,
                            "wfps": w,
                            "ph": p,
                            "weight": wgt,
                            "monod": monod,
                        },
                    )
                )

    def daily_step_layers(
        self,
        *,
        temperature_c: float,
        wfps_by_layer: List[float],
        ph_by_layer: List[float],
    ) -> None:
        """Depth-aware daily step using per-layer moisture (WFPS) and pH.

        Args:
            temperature_c: Mean canopy/soil temperature for the day.
            wfps_by_layer: Water-filled pore space per layer in [0, 1].
            ph_by_layer: Soil pH per layer.
        """
        norm_weights = self._normalize_enzyme_weights()

        for idx, layer in enumerate(self.state.layers):
            w = wfps_by_layer[idx if idx < len(wfps_by_layer) else -1]
            p = ph_by_layer[idx if idx < len(ph_by_layer) else -1]
            activity = self._compute_layer_activity(idx, w, p, temperature_c)
            self.event_bus.emit(
                MicrobialActivityComputed(
                    layer=idx,
                    activity_index=activity,
                    wfps=w,
                    ph=p,
                    temperature_c=temperature_c,
                )
            )
            self._adjust_fb_ratio(idx, layer, w, p)
            self._apply_mortality(idx, layer, activity)
            self._apply_growth_and_enzymes(
                idx, layer, activity, w, p, temperature_c, norm_weights
            )
        # Reset transient inputs after completing daily step
        self._substrate_today.clear()
        self._priming_multiplier.clear()
