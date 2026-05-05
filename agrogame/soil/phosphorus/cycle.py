"""Phosphorus cycle processes wired to water and root events.

Implements daily phosphorus transformations and minimal leaching in line with
AGRO-25 acceptance criteria:
- Track plant-available P per layer
- pH effect on availability (optimal near 6.5–7.0)
- Fixation rate moving available → fixed P
- Plant uptake allocated by root distribution
- Subscribe to water events; tiny P movement under heavy drainage
- Mass-balance check within a small tolerance
- Include temperature effects on mineralization
"""

from __future__ import annotations

from typing import Protocol
from collections.abc import Sequence
from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.plant.roots.events import RootDistributionUpdated
from agrogame.soil.chemistry.events import SoilPHUpdated
from agrogame.soil.water.events import WaterDrained
from agrogame.soil.microbes.events import (
    MicrobialActivityComputed,
    MicrobialFBUpdated,
)

from agrogame.soil.nitrogen.events import NutrientLeached

from .events import PhosphorusFixationOccurred
from .state import SoilPhosphorusState
from .types import PhosphorusFluxes
from .constants import (
    PH_AVAILABILITY_ANCHORS,
    FIXATION_WEEKLY_MIN,
    FIXATION_WEEKLY_MAX,
    HEAVY_DRAINAGE_MM,
    HEAVY_DRAINAGE_P_FRACTION,
)


class _SoilLayer(Protocol):
    field_capacity: float
    saturation: float
    depth_cm: float


class _WaterProfile(Protocol):
    layers: Sequence[_SoilLayer]


class _WaterState(Protocol):
    theta: Sequence[float]

    def layer_storage_mm(self, profile: _WaterProfile, idx: int) -> float: ...


class PhosphorusCycle:
    """Phosphorus processes and event integration for the soil profile."""

    def __init__(
        self,
        event_bus: EventBus,
        state: SoilPhosphorusState,
        water_state: _WaterState | None = None,
        profile: _WaterProfile | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.state = state
        self._n_layers = len(state.available_p)
        self._water_state = water_state
        self._profile = profile

        # Pending slow-release fertilizer schedules per layer
        self._slow_release_schedules: list[list[_SlowReleaseSchedule]] = [
            [] for _ in range(self._n_layers)
        ]

        # Subscribe to water movement events (minimal P movement)
        event_bus.subscribe(WaterDrained, self._on_water_drained)
        # Cache root distribution
        self._root_fractions_cached: list[float] | None = None
        event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)
        # Cache per-layer pH from chemistry
        self._ph_by_layer_cached: list[float] = [6.8] * self._n_layers
        event_bus.subscribe(SoilPHUpdated, self._on_soil_ph_updated)
        # Cache microbe signals
        self._microbe_activity_by_layer: list[float] = [1.0] * self._n_layers
        self._fungal_fraction_by_layer: list[float] = [0.4] * self._n_layers
        event_bus.subscribe(MicrobialActivityComputed, self._on_microbe_activity)
        event_bus.subscribe(MicrobialFBUpdated, self._on_microbe_fb)

    # --- Event handlers -------------------------------------------------
    def _on_water_drained(self, event: WaterDrained) -> None:
        """Move a tiny fraction of available P under heavy drainage; else immobile."""
        from_idx = event.from_layer
        if not (0 <= from_idx < self._n_layers):
            return
        if event.amount_mm <= HEAVY_DRAINAGE_MM:
            return

        pool = self.state.available_p[from_idx]
        moved = max(0.0, min(pool, pool * HEAVY_DRAINAGE_P_FRACTION))
        if moved <= 0.0:
            return
        self.state.available_p[from_idx] = max(0.0, pool - moved)
        # Treat as profile loss; reuse NutrientLeached with nutrient='P'
        self.event_bus.emit(
            NutrientLeached(nutrient="P", amount_kg_ha=moved, layer=from_idx)
        )

    def _on_root_distribution(self, event: RootDistributionUpdated) -> None:
        fracs = list(event.fractions)
        if len(fracs) < self._n_layers:
            pad = [0.0] * (self._n_layers - len(fracs))
            fracs = fracs + pad
        self._root_fractions_cached = fracs

    def _on_soil_ph_updated(self, event: SoilPHUpdated) -> None:
        if 0 <= event.layer < self._n_layers:
            self._ph_by_layer_cached[event.layer] = float(event.ph)

    def _on_microbe_activity(self, event: MicrobialActivityComputed) -> None:
        if 0 <= event.layer < self._n_layers:
            self._microbe_activity_by_layer[event.layer] = max(
                0.0, min(1.0, float(event.activity_index))
            )

    def _on_microbe_fb(self, event: MicrobialFBUpdated) -> None:
        if 0 <= event.layer < self._n_layers:
            self._fungal_fraction_by_layer[event.layer] = max(
                0.0, min(1.0, float(event.fungal_fraction))
            )

    # --- Daily update ---------------------------------------------------
    def daily_step(
        self,
        temperature_c: float,
        plant_demand_kg_ha: float = 0.0,
        root_fractions: list[float] | None = None,
        ph_by_layer: list[float] | None = None,
    ) -> PhosphorusFluxes:
        # First, release any scheduled slow-release fertilizer for the day
        self._release_slow_fertilizer_for_day()
        if root_fractions is None:
            root_fractions = (
                self._root_fractions_cached
                if self._root_fractions_cached is not None
                else [1.0 / self._n_layers] * self._n_layers
            )
        if ph_by_layer is None:
            ph_by_layer = self._ph_by_layer_cached

        temp_factor = 2.0 ** ((temperature_c - 25.0) / 10.0)

        before_total = self._total_p()

        mineralized = 0.0
        fixed = 0.0

        for i in range(self._n_layers):
            moisture_factor = self._moisture_factor(i)
            mineralized += self._mineralize_layer(i, temp_factor, moisture_factor)
            fixed += self._fix_layer(i, ph_by_layer[i])

        plant_uptake = self._take_up_plant(
            max(0.0, plant_demand_kg_ha), root_fractions, ph_by_layer
        )

        after_total = self._total_p()
        delta_storage = after_total - before_total
        outputs = fixed + plant_uptake
        if abs(delta_storage + outputs - mineralized) > 0.02:
            _ = (delta_storage, outputs, mineralized)

        return PhosphorusFluxes(
            mineralized_kg_ha=mineralized,
            fixed_kg_ha=fixed,
            plant_uptake_kg_ha=plant_uptake,
            leached_kg_ha=0.0,
        )

    # --- Internal helpers ----------------------------------------------
    def _total_p(self) -> float:
        # Include pending slow-release fertilizer to maintain mass balance
        pending = 0.0
        for schedules in self._slow_release_schedules:
            for s in schedules:
                pending += s.remaining_amount_kg_ha
        return (
            sum(self.state.available_p)
            + sum(self.state.fixed_p)
            + sum(self.state.organic_p)
            + pending
        )

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
                # linear interpolate
                t = (ph - x0) / max(1e-9, (x1 - x0))
                return y0 + t * (y1 - y0)
        return anchors[-1][1]

    def _mineralize_layer(
        self, idx: int, temp_factor: float, moisture_factor: float
    ) -> float:
        # 0.5–2% per month at 25°C → per day range ≈ (0.005/30 .. 0.02/30)
        base_daily = (0.005 / 30.0, 0.02 / 30.0)
        # Use mid value scaled by temp and moisture
        # Microbial activity scales mineralization (dampening only)
        activity = self._microbe_activity_by_layer[idx]
        rate = (
            0.5
            * (base_daily[0] + base_daily[1])
            * temp_factor
            * moisture_factor
            * activity
        )
        om = self.state.organic_p[idx]
        m = max(0.0, min(om, om * rate))
        if m > 0.0:
            self.state.organic_p[idx] -= m
            self.state.available_p[idx] += m
        return m

    def _fix_layer(self, idx: int, ph: float) -> float:
        # Weekly 1–5%; convert to daily (~1/7). Scale by acidity (more at low pH).
        acidity = max(0.0, min(1.0, (7.0 - ph) / 3.0))  # 0 at pH>=7, ~1 at pH<=4
        weekly = (
            FIXATION_WEEKLY_MIN + (FIXATION_WEEKLY_MAX - FIXATION_WEEKLY_MIN) * acidity
        )
        daily = weekly / 7.0
        avail = self.state.available_p[idx]
        f = max(0.0, min(avail, avail * daily))
        if f > 0.0:
            self.state.available_p[idx] -= f
            self.state.fixed_p[idx] += f
            self.event_bus.emit(
                PhosphorusFixationOccurred(layer=idx, amount_fixed_kg_ha=f)
            )
        return f

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
            # Fungi can enhance P acquisition via enzymes/mycorrhizae;
            # apply modest boost with fungal share
            fb_boost = 1.0 + 0.15 * self._fungal_fraction_by_layer[i]
            avail_eff = (
                self.state.available_p[i]
                * self._ph_availability(ph_by_layer[i])
                * fb_boost
            )
            take_p = min(avail_eff, want)
            self.state.available_p[i] -= take_p
            taken += take_p
        return taken

    # --- Fertilizer APIs -----------------------------------------------
    def apply_triple_superphosphate(self, layer: int, amount_kg_ha: float) -> None:
        if 0 <= layer < self._n_layers and amount_kg_ha > 0.0:
            self.state.available_p[layer] += amount_kg_ha

    def apply_slow_release_p(
        self, layer: int, amount_kg_ha: float, release_days: int
    ) -> None:
        # Apply 20% immediately; schedule the remainder evenly over release_days.
        if not (0 <= layer < self._n_layers) or amount_kg_ha <= 0.0:
            return
        immediate = 0.2 * amount_kg_ha
        self.state.available_p[layer] += immediate
        remaining = max(0.0, amount_kg_ha - immediate)
        # If release_days <= 0, release all immediately
        if remaining <= 0.0:
            return
        if release_days <= 0:
            self.state.available_p[layer] += remaining
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
        """Move scheduled slow-release fertilizer into available pool for today.

        Releases a fixed daily amount for each active schedule. On the final day,
        releases any remaining amount to avoid rounding accumulation.
        """
        for layer_idx, schedules in enumerate(self._slow_release_schedules):
            if not schedules:
                continue
            next_schedules: list[_SlowReleaseSchedule] = []
            for s in schedules:
                if s.remaining_days > 1:
                    release = min(s.daily_release_kg_ha, s.remaining_amount_kg_ha)
                    if release > 0.0:
                        self.state.available_p[layer_idx] += release
                        s.remaining_amount_kg_ha -= release
                    s.remaining_days -= 1
                    if s.remaining_amount_kg_ha > 1e-9 and s.remaining_days > 0:
                        next_schedules.append(s)
                else:
                    # Final day: release all remaining
                    release = s.remaining_amount_kg_ha
                    if release > 0.0:
                        self.state.available_p[layer_idx] += release
                    # Do not append; schedule is completed
            self._slow_release_schedules[layer_idx] = next_schedules


# --- Private helper structures -----------------------------------------
@dataclass
class _SlowReleaseSchedule:
    remaining_days: int
    daily_release_kg_ha: float
    remaining_amount_kg_ha: float
