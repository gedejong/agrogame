from __future__ import annotations

from dataclasses import dataclass
from typing import List

from agrogame.events import EventBus
from .events import EnzymeProduced, MicrobialGrowth, MicrobialMortality
from .responses import EnvironmentalResponses


@dataclass
class MicrobialParams:
    n_layers: int
    cn_ratio: float = 8.0
    bacteria_turnover_days: float = 30.0
    fungi_turnover_days: float = 120.0
    enzyme_cost_fraction: float = 0.1  # fraction of C uptake


@dataclass
class MicrobialLayerState:
    c_kg_ha: float = 200.0
    n_kg_ha: float = 25.0
    fungal_fraction: float = 0.4  # remainder bacterial


@dataclass
class MicrobialState:
    layers: List[MicrobialLayerState]


class MicrobialBiomassModule:
    def __init__(self, params: MicrobialParams, event_bus: EventBus) -> None:
        self.params = params
        self.event_bus = event_bus
        self.responses = EnvironmentalResponses()
        self.state = MicrobialState(
            layers=[MicrobialLayerState() for _ in range(params.n_layers)]
        )

    def daily_step(self, temperature_c: float, wfps: float, ph: float) -> None:
        """Very simplified growth/turnover placeholder.

        This will be expanded to couple to SOM decomposition and enzyme kinetics.
        """
        for idx, layer in enumerate(self.state.layers):
            temp_mod = self.responses.temperature_modifier(temperature_c)
            moist_mod = self.responses.moisture_modifier(wfps)
            ph_mod = self.responses.ph_modifier(ph)
            activity = max(0.0, temp_mod * moist_mod * ph_mod)

            # Turnover
            bact_frac = 1.0 - layer.fungal_fraction
            bact_k = min(1.0, 1.0 / max(1e-6, self.params.bacteria_turnover_days))
            fungi_k = min(1.0, 1.0 / max(1e-6, self.params.fungi_turnover_days))
            daily_mortality_c = activity * (
                layer.c_kg_ha * (bact_frac * bact_k + layer.fungal_fraction * fungi_k)
            )
            if daily_mortality_c > 0.0:
                n_mort = daily_mortality_c / max(1e-6, self.params.cn_ratio)
                layer.c_kg_ha -= daily_mortality_c
                layer.n_kg_ha -= n_mort
                self.event_bus.emit(
                    MicrobialMortality(
                        layer=idx,
                        c_to_som_kg_ha=daily_mortality_c,
                        n_to_som_kg_ha=n_mort,
                    )
                )

            # Placeholder growth from substrate (to be wired to SOM)
            potential_growth_c = activity * 5.0  # kg C/ha/day placeholder
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
                self.event_bus.emit(
                    EnzymeProduced(
                        layer=idx,
                        enzyme_group="pooled",
                        production_cost_c_kg_ha=enzyme_cost,
                        params={"activity": activity},
                    )
                )
