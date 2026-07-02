"""Shared per-layer environmental cache for the nutrient cycles (#322).

The nitrogen, phosphorus and micronutrient cycles all need to track the
same slowly-varying environmental signals — soil pH, root distribution,
microbial activity index and the fungal:bacterial fraction — and to keep
them fresh by subscribing to the same domain events. Before this component
each cycle hand-rolled near-identical caches and handlers, so a bug fix or
a new signal had to be applied in up to three places and the magic default
values drifted (``[7.0]`` vs ``[6.8]`` for pH).

``EnvironmentalCache`` owns those caches and their event handlers and wires
them to the bus. Cycles compose it and read the cached lists directly.
Per-cycle defaults (e.g. initial pH) stay configurable so behaviour is
unchanged, and the root-distribution normalisation policy is selectable to
match each cycle's historical handling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agrogame.events import EventBus

if TYPE_CHECKING:
    from agrogame.plant.roots.events import RootDistributionUpdated
    from agrogame.soil.chemistry.events import SoilPHUpdated
    from agrogame.soil.microbes.events import (
        MicrobialActivityComputed,
        MicrobialFBUpdated,
    )


class EnvironmentalCache:
    """Per-layer environmental signals shared across nutrient cycles.

    Owns the pH / root-fraction / microbe-activity / fungal-fraction caches
    and the four event handlers that keep them current, subscribing the
    requested subset to the bus.

    The cached lists are exposed as public attributes so the owning cycle
    can read (and, for the historical test hooks, mutate) them in place:

    - ``ph_by_layer``: list[float], length ``n_layers``.
    - ``root_fractions``: list[float] | None — ``None`` until the first
      ``RootDistributionUpdated`` is seen.
    - ``microbe_activity_by_layer``: list[float] in ``[0, 1]``.
    - ``fungal_fraction_by_layer``: list[float] in ``[0, 1]``.

    Args:
        event_bus: Bus to subscribe the enabled handlers to.
        n_layers: Number of soil layers.
        initial_ph: Default pH seeded into every layer (7.0 for N, 6.8 for
            P and micronutrients) — kept configurable so no behaviour change.
        initial_microbe_activity: Default activity index per layer.
        initial_fungal_fraction: Default fungal:bacterial fraction per layer.
        normalize_root_fractions: When ``True`` (nitrogen), incoming root
            fractions are clamped to non-negative, renormalised to sum 1.0
            and trimmed/padded to ``n_layers``. When ``False`` (phosphorus),
            fractions are stored as received, padded (never trimmed) to at
            least ``n_layers``.
        subscribe_ph: Subscribe the pH handler.
        subscribe_roots: Subscribe the root-distribution handler.
        subscribe_microbes: Subscribe the microbe activity + F:B handlers.
    """

    def __init__(
        self,
        event_bus: EventBus,
        n_layers: int,
        *,
        initial_ph: float = 7.0,
        initial_microbe_activity: float = 1.0,
        initial_fungal_fraction: float = 0.4,
        normalize_root_fractions: bool = True,
        subscribe_ph: bool = True,
        subscribe_roots: bool = True,
        subscribe_microbes: bool = True,
    ) -> None:
        # Local imports avoid a package-init import cycle: importing the
        # chemistry/microbes/roots event packages at module load time would
        # pull their ``__init__`` chains (chemistry → phosphorus → nutrients)
        # before this package finishes initialising (#322).
        from agrogame.plant.roots.events import RootDistributionUpdated
        from agrogame.soil.chemistry.events import SoilPHUpdated
        from agrogame.soil.microbes.events import (
            MicrobialActivityComputed,
            MicrobialFBUpdated,
        )

        self._n_layers = n_layers
        self._normalize_root_fractions = normalize_root_fractions

        self.ph_by_layer: list[float] = [initial_ph] * n_layers
        self.root_fractions: list[float] | None = None
        self.microbe_activity_by_layer: list[float] = [
            initial_microbe_activity
        ] * n_layers
        self.fungal_fraction_by_layer: list[float] = [
            initial_fungal_fraction
        ] * n_layers

        if subscribe_ph:
            event_bus.subscribe(SoilPHUpdated, self._on_soil_ph_updated)
        if subscribe_roots:
            event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)
        if subscribe_microbes:
            event_bus.subscribe(MicrobialActivityComputed, self._on_microbe_activity)
            event_bus.subscribe(MicrobialFBUpdated, self._on_microbe_fb)

    # --- Event handlers -------------------------------------------------
    def _on_soil_ph_updated(self, event: SoilPHUpdated) -> None:
        if 0 <= event.layer < self._n_layers:
            self.ph_by_layer[event.layer] = float(event.ph)

    def _on_root_distribution(self, event: RootDistributionUpdated) -> None:
        if self._normalize_root_fractions:
            fracs = [max(0.0, f) for f in event.fractions]
            s = sum(fracs) or 1.0
            fracs = [f / s for f in fracs]
            if len(fracs) >= self._n_layers:
                self.root_fractions = fracs[: self._n_layers]
            else:
                pad = [0.0] * (self._n_layers - len(fracs))
                self.root_fractions = fracs + pad
        else:
            fracs = list(event.fractions)
            if len(fracs) < self._n_layers:
                fracs = fracs + [0.0] * (self._n_layers - len(fracs))
            self.root_fractions = fracs

    def _on_microbe_activity(self, event: MicrobialActivityComputed) -> None:
        if 0 <= event.layer < self._n_layers:
            # Clamp to [0, 1] so microbes can only dampen rates, not blow them up
            self.microbe_activity_by_layer[event.layer] = max(
                0.0, min(1.0, float(event.activity_index))
            )

    def _on_microbe_fb(self, event: MicrobialFBUpdated) -> None:
        if 0 <= event.layer < self._n_layers:
            self.fungal_fraction_by_layer[event.layer] = max(
                0.0, min(1.0, float(event.fungal_fraction))
            )
