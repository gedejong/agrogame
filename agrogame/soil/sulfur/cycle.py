"""Sulfur cycle processes wired to water and root events (non-redox).

Implements daily sulfur transformations in line with issue #212:
- Track SO4 (available), adsorbed and organic S pools per layer
- Organic-S mineralization (temperature/moisture/microbe scaled)
- Reversible SO4 adsorption/desorption (pH + Fe/Al-oxide/clay dependent)
- Plant uptake allocated by root distribution and pH availability
- Sulfate leaching driven by ``WaterDrained`` (mobile — nitrate-like)
- Fertilizer additions (gypsum, elemental S)
- Mass-balance check within a small tolerance

Explicitly EXCLUDES redox pathways (sulfate reduction, sulfide oxidation);
those live in a separate sub-issue.
"""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.soil.water.events import WaterDrained
from agrogame.soil.nutrients import EnvironmentalCache

from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.params.ports import SoilProfileView, WaterState

from .events import SulfurAdsorbed, SulfurMineralized
from .params import SulfurRateParams
from .state import SoilSulfurState
from .types import SulfurFluxes
from .constants import PH_AVAILABILITY_ANCHORS


class SulfurCycle:
    """Sulfur processes and event integration for the soil profile."""

    def __init__(
        self,
        event_bus: EventBus,
        state: SoilSulfurState,
        water_state: WaterState | None = None,
        profile: SoilProfileView | None = None,
        params: SulfurRateParams | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.state = state
        self._n_layers = len(state.available_s)
        self._water_state = water_state
        self._profile = profile
        self._params = params if params is not None else SulfurRateParams()

        # Pending slow-release (elemental-S oxidation proxy) schedules per layer
        self._slow_release_schedules: list[list[_SlowReleaseSchedule]] = [
            [] for _ in range(self._n_layers)
        ]

        # Subscribe to water movement events (mobile sulfate leaching)
        event_bus.subscribe(WaterDrained, self._on_water_drained)
        # Shared per-layer environmental cache (#322): pH, root fractions,
        # microbe activity and fungal fraction. Sulfur mirrors phosphorus:
        # defaults pH to 6.8 and stores root fractions without renormalising.
        self._env = EnvironmentalCache(
            event_bus,
            self._n_layers,
            initial_ph=6.8,
            normalize_root_fractions=False,
        )

    # --- Event handlers -------------------------------------------------
    def _on_water_drained(self, event: WaterDrained) -> None:
        """Move SO4 with drainage proportionally to water fraction (mobile).

        Sulfate is only weakly retained, so it leaches like nitrate: the
        fraction moved equals ``drainage_mm / storage_mm``. When the
        destination layer is outside the profile, emit a leaching loss.
        """
        from_idx = event.from_layer
        to_idx = event.to_layer
        if not (0 <= from_idx < self._n_layers):
            return

        storage_mm = self._get_layer_storage_mm(from_idx)
        if storage_mm <= 0.0:
            return

        fraction = max(0.0, min(1.0, event.amount_mm / storage_mm))
        if fraction <= 0.0:
            return

        pool = self.state.available_s[from_idx]
        moved = fraction * pool
        if moved <= 0.0:
            return

        self.state.available_s[from_idx] = max(0.0, pool - moved)
        if 0 <= to_idx < self._n_layers:
            self.state.available_s[to_idx] += moved
        else:
            self.event_bus.emit(
                NutrientLeached(nutrient="SO4", amount_kg_ha=moved, layer=from_idx)
            )

    # --- Daily update ---------------------------------------------------
    def daily_step(
        self,
        temperature_c: float,
        plant_demand_kg_ha: float = 0.0,
        root_fractions: list[float] | None = None,
        ph_by_layer: list[float] | None = None,
    ) -> SulfurFluxes:
        # First, release any scheduled slow-release (elemental S) for the day
        self._release_slow_fertilizer_for_day()
        if root_fractions is None:
            root_fractions = (
                self._env.root_fractions
                if self._env.root_fractions is not None
                else [1.0 / self._n_layers] * self._n_layers
            )
        if ph_by_layer is None:
            ph_by_layer = self._env.ph_by_layer

        temp_factor = 2.0 ** ((temperature_c - 25.0) / 10.0)

        mineralized = 0.0
        adsorbed = 0.0

        for i in range(self._n_layers):
            moisture_factor = self._moisture_factor(i)
            mineralized += self._mineralize_layer(i, temp_factor, moisture_factor)
            adsorbed += self._adsorb_layer(i, ph_by_layer[i])

        plant_uptake = self._take_up_plant(
            max(0.0, plant_demand_kg_ha), root_fractions, ph_by_layer
        )

        return SulfurFluxes(
            mineralized_kg_ha=mineralized,
            adsorbed_kg_ha=adsorbed,
            plant_uptake_kg_ha=plant_uptake,
            leached_kg_ha=0.0,
        )

    # --- Internal helpers ----------------------------------------------
    def _total_s(self) -> float:
        # Include pending slow-release fertilizer to maintain mass balance
        pending = 0.0
        for schedules in self._slow_release_schedules:
            for s in schedules:
                pending += s.remaining_amount_kg_ha
        return (
            sum(self.state.available_s)
            + sum(self.state.adsorbed_s)
            + sum(self.state.organic_s)
            + pending
        )

    def _layer_clay_pct(self, idx: int) -> float | None:
        """Return clay % for a layer, or None when unavailable.

        Returning None keeps texture modulation neutral (multiplier 1.0) so
        cycles built without a profile (e.g. unit tests) are unchanged.
        """
        if self._profile is None or not (0 <= idx < len(self._profile.layers)):
            return None
        return getattr(self._profile.layers[idx], "clay_pct", None)

    @staticmethod
    def _clay_multiplier(
        clay_pct: float | None,
        reference_pct: float,
        sensitivity: float,
        min_mult: float,
        max_mult: float,
    ) -> float:
        """Reference-normalized linear clay response, clamped to bounds."""
        if clay_pct is None or reference_pct <= 0.0:
            return 1.0
        mult = 1.0 + sensitivity * (clay_pct - reference_pct) / reference_pct
        return max(min_mult, min(max_mult, mult))

    def _get_layer_storage_mm(self, idx: int) -> float:
        if self._water_state is None or self._profile is None:
            # Fallback nominal storage to avoid division by zero in tests
            return 100.0
        return self._water_state.layer_storage_mm(self._profile, idx)

    def _moisture_factor(self, idx: int) -> float:
        if self._water_state is None or self._profile is None:
            return 1.0
        layer = self._profile.layers[idx]
        theta = self._water_state.theta[idx]
        if layer.field_capacity <= 0:
            return 1.0
        return max(0.3, min(1.0, theta / layer.field_capacity))

    @staticmethod
    def _ph_availability(ph: float) -> float:
        # Piecewise-linear interpolation on anchors
        anchors = PH_AVAILABILITY_ANCHORS
        if ph <= anchors[0][0]:
            return anchors[0][1]
        from itertools import pairwise

        for (x0, y0), (x1, y1) in pairwise(anchors):
            if ph <= x1:
                t = (ph - x0) / max(1e-9, (x1 - x0))
                return y0 + t * (y1 - y0)
        return anchors[-1][1]

    def _mineralize_layer(
        self, idx: int, temp_factor: float, moisture_factor: float
    ) -> float:
        # Monthly mineralization bounds → per-day midpoint (÷30), scaled by
        # temperature, moisture and microbial activity (dampening only).
        base_daily_min = self._params.mineralization_monthly_min / 30.0
        base_daily_max = self._params.mineralization_monthly_max / 30.0
        activity = self._env.microbe_activity_by_layer[idx]
        rate = (
            0.5 * (base_daily_min + base_daily_max) * temp_factor * moisture_factor
        ) * activity
        om = self.state.organic_s[idx]
        m = max(0.0, min(om, om * rate))
        if m > 0.0:
            self.state.organic_s[idx] -= m
            self.state.available_s[idx] += m
            self.event_bus.emit(SulfurMineralized(layer=idx, amount_kg_ha=m))
        return m

    def _adsorb_layer(self, idx: int, ph: float) -> float:
        """Reversible SO4 adsorption/desorption for a layer.

        Adsorption pulls SO4 from solution (stronger at low pH and on
        oxide-rich/clayey soils), while a smaller desorption term releases
        adsorbed SO4 back — the labile equilibrium that distinguishes
        sulfate from near-permanent phosphate fixation. Returns the *net*
        S moved into the adsorbed pool (negative under net desorption).
        """
        acidity = max(0.0, min(1.0, (7.0 - ph) / 3.0))  # 0 at pH>=7, ~1 at pH<=4
        weekly = (
            self._params.adsorption_weekly_min
            + (self._params.adsorption_weekly_max - self._params.adsorption_weekly_min)
            * acidity
        )
        clay_mult = self._clay_multiplier(
            self._layer_clay_pct(idx),
            self._params.adsorption_clay_reference_pct,
            self._params.adsorption_clay_sensitivity,
            self._params.adsorption_clay_min_mult,
            self._params.adsorption_clay_max_mult,
        )
        avail = self.state.available_s[idx]
        adsorb = max(0.0, min(avail, avail * weekly * clay_mult / 7.0))
        desorb = max(
            0.0,
            min(
                self.state.adsorbed_s[idx],
                self.state.adsorbed_s[idx] * self._params.desorption_weekly / 7.0,
            ),
        )
        net = adsorb - desorb
        if net == 0.0:
            return 0.0
        self.state.available_s[idx] -= net
        self.state.adsorbed_s[idx] += net
        self.event_bus.emit(SulfurAdsorbed(layer=idx, amount_kg_ha=net))
        return net

    def _take_up_plant(
        self, total_demand: float, root_fractions: list[float], ph_by_layer: list[float]
    ) -> float:
        if total_demand <= 0.0:
            return 0.0
        s = sum(x for x in root_fractions if x > 0.0) or 1.0
        shares = [max(0.0, x) / s for x in root_fractions]
        wants = [total_demand * share for share in shares]
        taken = 0.0
        for i, want in enumerate(wants):
            if want <= 0.0:
                continue
            avail_eff = self.state.available_s[i] * self._ph_availability(
                ph_by_layer[i]
            )
            take_s = min(avail_eff, want)
            self.state.available_s[i] -= take_s
            taken += take_s
        return taken

    # --- Fertilizer APIs -----------------------------------------------
    def apply_gypsum(self, layer: int, amount_kg_s_ha: float) -> None:
        """Apply gypsum (CaSO4·2H2O) S — immediately plant-available sulfate.

        Args:
            layer: Target soil layer index.
            amount_kg_s_ha: Sulfur application rate (kg S/ha).
        """
        if 0 <= layer < self._n_layers and amount_kg_s_ha > 0.0:
            self.state.available_s[layer] += amount_kg_s_ha

    def apply_elemental_s(
        self, layer: int, amount_kg_s_ha: float, release_days: int = 60
    ) -> None:
        """Apply elemental S, released gradually as microbial oxidation to SO4.

        The oxidation of S(0) to sulfate is a slow, biologically mediated
        process (weeks-months); we model it as a slow-release schedule into
        the available pool rather than a redox Eh computation (kept out of
        scope per #212). A small immediate fraction represents readily
        oxidisable fines.

        Args:
            layer: Target soil layer index.
            amount_kg_s_ha: Sulfur application rate (kg S/ha).
            release_days: Days over which the remainder oxidizes to SO4.
        """
        if not (0 <= layer < self._n_layers) or amount_kg_s_ha <= 0.0:
            return
        immediate = 0.05 * amount_kg_s_ha
        self.state.available_s[layer] += immediate
        remaining = max(0.0, amount_kg_s_ha - immediate)
        if remaining <= 0.0:
            return
        if release_days <= 0:
            self.state.available_s[layer] += remaining
            return
        daily = remaining / float(release_days)
        self._slow_release_schedules[layer].append(
            _SlowReleaseSchedule(
                remaining_days=release_days,
                daily_release_kg_ha=daily,
                remaining_amount_kg_ha=remaining,
            )
        )

    # --- Slow-release internal mechanics -------------------------------
    def _release_slow_fertilizer_for_day(self) -> None:
        """Move scheduled elemental-S oxidation into the SO4 pool for today."""
        for layer_idx, schedules in enumerate(self._slow_release_schedules):
            if not schedules:
                continue
            next_schedules: list[_SlowReleaseSchedule] = []
            for s in schedules:
                if s.remaining_days > 1:
                    release = min(s.daily_release_kg_ha, s.remaining_amount_kg_ha)
                    if release > 0.0:
                        self.state.available_s[layer_idx] += release
                        s.remaining_amount_kg_ha -= release
                    s.remaining_days -= 1
                    if s.remaining_amount_kg_ha > 1e-9 and s.remaining_days > 0:
                        next_schedules.append(s)
                else:
                    # Final day: release all remaining
                    release = s.remaining_amount_kg_ha
                    if release > 0.0:
                        self.state.available_s[layer_idx] += release
            self._slow_release_schedules[layer_idx] = next_schedules


# --- Private helper structures -----------------------------------------
@dataclass
class _SlowReleaseSchedule:
    remaining_days: int
    daily_release_kg_ha: float
    remaining_amount_kg_ha: float
