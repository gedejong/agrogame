"""Micronutrient cycling — pH-dependent availability, OM complexation, uptake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agrogame.events import EventBus
from agrogame.plant.events import NutrientStressComputed
from agrogame.soil.micronutrients.constants import (
    PH_AVAIL_FE,
    PH_AVAIL_MN,
    PH_AVAIL_ZN,
)
from agrogame.soil.micronutrients.params import MicronutrientParams
from agrogame.soil.micronutrients.state import MicronutrientState


@dataclass
class MicronutrientFluxes:
    """Summary of daily micronutrient fluxes."""

    fe_uptake_g_ha: float = 0.0
    zn_uptake_g_ha: float = 0.0
    mn_uptake_g_ha: float = 0.0
    fe_stress: float = 1.0
    zn_stress: float = 1.0
    mn_stress: float = 1.0


class MicronutrientCycle:
    """Daily micronutrient processes: availability, complexation, uptake.

    Ref: Lindsay 1979, Chemical Equilibria in Soils;
         Alloway 2008, Micronutrient Deficiencies in Global Crop Production.
    """

    def __init__(
        self,
        event_bus: EventBus,
        state: MicronutrientState,
        params: MicronutrientParams,
        n_layers: int,
    ) -> None:
        self.event_bus = event_bus
        self.state = state
        self.params = params
        self._n_layers = n_layers
        self._ph_by_layer: list[float] = [6.8] * n_layers
        self._som_c_by_layer: list[float] = [0.0] * n_layers
        # Subscribe to pH updates
        from agrogame.soil.chemistry.events import SoilPHUpdated

        event_bus.subscribe(SoilPHUpdated, self._on_ph_updated)

    def _on_ph_updated(self, ev: object) -> None:
        layer = getattr(ev, "layer", None)
        ph = getattr(ev, "ph", None)
        if layer is not None and ph is not None and layer < self._n_layers:
            self._ph_by_layer[layer] = float(ph)

    def set_som_c(self, som_c_by_layer: list[float]) -> None:
        """Update SOM carbon for complexation calculation."""
        self._som_c_by_layer = list(som_c_by_layer)

    def daily_step(
        self,
        biomass_inc_g_m2: float = 0.0,
        root_fractions: Optional[list[float]] = None,
    ) -> MicronutrientFluxes:
        """Process daily micronutrient availability and plant uptake.

        Args:
            biomass_inc_g_m2: Daily biomass increment for demand scaling.
            root_fractions: Root density per layer for uptake allocation.
        """
        p = self.params
        if root_fractions is None:
            root_fractions = [1.0 / self._n_layers] * self._n_layers

        # Update availability based on pH and OM complexation
        for i in range(self._n_layers):
            ph = self._ph_by_layer[i]
            som_c = self._som_c_by_layer[i] if i < len(self._som_c_by_layer) else 0.0
            self._update_availability(i, ph, som_c)

        # Daily demand = season demand / season_days, scaled by growth rate
        growth_scale = max(0.01, biomass_inc_g_m2 / 30.0)  # ~30 g/m2 peak
        daily_fe = (p.demand_fe_g_ha / p.season_days) * growth_scale
        daily_zn = (p.demand_zn_g_ha / p.season_days) * growth_scale
        daily_mn = (p.demand_mn_g_ha / p.season_days) * growth_scale

        # Uptake from available pools
        fe_up = self._take_up("fe", daily_fe, root_fractions)
        zn_up = self._take_up("zn", daily_zn, root_fractions)
        mn_up = self._take_up("mn", daily_mn, root_fractions)

        # Compute stress factors
        fe_stress = self._compute_stress("fe", fe_up, daily_fe)
        zn_stress = self._compute_stress("zn", zn_up, daily_zn)
        mn_stress = self._compute_stress("mn", mn_up, daily_mn)

        # Emit stress events
        self._emit_stress("Fe", fe_up, daily_fe, fe_stress)
        self._emit_stress("Zn", zn_up, daily_zn, zn_stress)
        self._emit_stress("Mn", mn_up, daily_mn, mn_stress)

        return MicronutrientFluxes(
            fe_uptake_g_ha=fe_up,
            zn_uptake_g_ha=zn_up,
            mn_uptake_g_ha=mn_up,
            fe_stress=fe_stress,
            zn_stress=zn_stress,
            mn_stress=mn_stress,
        )

    def apply_amendment(self, element: str, amount_g_ha: float, layer: int = 0) -> None:
        """Apply micronutrient fertilizer to a soil layer.

        Args:
            element: "fe", "zn", or "mn".
            amount_g_ha: Amount in g/ha.
            layer: Target soil layer (default 0 = top).
        """
        if layer >= self._n_layers:
            return
        # Convert g/ha to ppm: ppm = g_ha / (bulk_density * depth * 10)
        from agrogame.soil.micronutrients.constants import (
            BULK_DENSITY_KG_M3,
            DEFAULT_LAYER_DEPTH_CM,
        )

        ppm = amount_g_ha / (BULK_DENSITY_KG_M3 * DEFAULT_LAYER_DEPTH_CM * 0.01)
        avail = getattr(self.state, f"{element}_available", None)
        total = getattr(self.state, f"{element}_total", None)
        if avail is not None and total is not None and layer < len(avail):
            avail[layer] += ppm
            total[layer] += ppm

    # --- Internal ---

    def _update_availability(self, layer: int, ph: float, som_c: float) -> None:
        """Adjust available pools based on pH, OM, and weathering equilibrium.

        Available pool equilibrates toward target determined by total pool
        × pH multiplier × OM factor. Represents mineral weathering/dissolution.
        Ref: Lindsay 1979 — equilibrium solubility controls.
        """
        from agrogame.soil.micronutrients.constants import (
            DEFAULT_AVAIL_FRACTION_FE,
            DEFAULT_AVAIL_FRACTION_MN,
            DEFAULT_AVAIL_FRACTION_ZN,
        )

        base_fracs = {
            "fe": DEFAULT_AVAIL_FRACTION_FE,
            "zn": DEFAULT_AVAIL_FRACTION_ZN,
            "mn": DEFAULT_AVAIL_FRACTION_MN,
        }
        for elem, table in [
            ("fe", PH_AVAIL_FE),
            ("zn", PH_AVAIL_ZN),
            ("mn", PH_AVAIL_MN),
        ]:
            total = getattr(self.state, f"{elem}_total")[layer]
            avail_list = getattr(self.state, f"{elem}_available")
            ph_mult = _interpolate_ph(ph, table)
            om_factor = max(0.1, 1.0 - self.params.om_complexation_factor * som_c)
            target = total * base_fracs[elem] * ph_mult * om_factor
            # Equilibrate toward target (tau ~10 days)
            current = avail_list[layer]
            avail_list[layer] = current + 0.1 * (target - current)

    def _take_up(
        self, element: str, demand_g_ha: float, root_fractions: list[float]
    ) -> float:
        """Extract micronutrient from available pools by root distribution."""
        if demand_g_ha <= 0.0:
            return 0.0
        from agrogame.soil.micronutrients.constants import (
            BULK_DENSITY_KG_M3,
            DEFAULT_LAYER_DEPTH_CM,
        )

        avail = getattr(self.state, f"{element}_available")
        taken_total = 0.0
        n = min(self._n_layers, len(root_fractions))
        for i in range(n):
            want = demand_g_ha * root_fractions[i]
            # Convert available ppm to g/ha for comparison
            avail_g_ha = avail[i] * BULK_DENSITY_KG_M3 * DEFAULT_LAYER_DEPTH_CM * 0.01
            take = min(want, avail_g_ha * 0.05)  # max 5% of pool per day
            # Convert back to ppm reduction
            ppm_taken = take / (BULK_DENSITY_KG_M3 * DEFAULT_LAYER_DEPTH_CM * 0.01)
            avail[i] = max(0.0, avail[i] - ppm_taken)
            taken_total += take
        return taken_total

    def _compute_stress(self, element: str, uptake: float, demand: float) -> float:
        """Compute stress factor from uptake/demand and pool levels.

        Combines supply-demand ratio with deficiency/toxicity thresholds.
        """
        # Supply-demand stress
        if demand <= 0.0:
            supply_stress = 1.0
        else:
            supply_stress = min(1.0, uptake / demand)
        # Deficiency stress from pool level (top layer)
        avail = getattr(self.state, f"{element}_available")
        top_ppm = avail[0] if avail else 0.0
        critical = getattr(self.params, f"critical_{element}_ppm")
        toxic = getattr(self.params, f"toxic_{element}_ppm")
        # Below critical: linear stress 0→1
        if top_ppm < critical:
            pool_stress = max(0.0, top_ppm / critical)
        elif top_ppm > toxic:
            # Toxicity: stress decreases above toxic threshold
            pool_stress = max(0.0, 1.0 - (top_ppm - toxic) / toxic)
        else:
            pool_stress = 1.0
        return float(min(supply_stress, pool_stress))

    def _emit_stress(
        self, nutrient: str, uptake: float, demand: float, stress: float
    ) -> None:
        self.event_bus.emit(
            NutrientStressComputed(
                nutrient=nutrient,
                uptake_kg_ha=uptake / 1000.0,  # g/ha → kg/ha
                demand_kg_ha=demand / 1000.0,
                stress=stress,
            )
        )


def _interpolate_ph(ph: float, table: list[tuple[float, float]]) -> float:
    """Piecewise-linear interpolation from pH-availability lookup table."""
    if ph <= table[0][0]:
        return table[0][1]
    if ph >= table[-1][0]:
        return table[-1][1]
    for i in range(len(table) - 1):
        if table[i][0] <= ph <= table[i + 1][0]:
            frac = (ph - table[i][0]) / (table[i + 1][0] - table[i][0])
            return table[i][1] + frac * (table[i + 1][1] - table[i][1])
    return 1.0
