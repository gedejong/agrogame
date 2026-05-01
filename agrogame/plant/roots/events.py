from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class RootDepthChanged(BaseEvent):
    previous_cm: float
    new_cm: float


@dataclass(frozen=True)
class RootDistributionUpdated(BaseEvent):
    fractions: tuple[float, ...]


@dataclass(frozen=True)
class RootBiomassUpdated(BaseEvent):
    biomass_g_m2: float


@dataclass(frozen=True)
class RootTurnoverOccurred(BaseEvent):
    """Daily root senescence — dead-root mass per soil layer.

    Emitted by ``RootModule._update_biomass`` when the bulk biomass
    turnover (``turnover_rate_per_day × biomass``) is split across
    layers using the current ``layer_fractions``. Consumed by the
    biopore module (#215) to convert dead root channels into
    persistent macropores.

    Attributes:
        per_layer_dead_mass_g_m2: Dead root mass by layer (g/m²).
            Tuple length matches the active root distribution layer
            count; sum equals the daily turnover total.
    """

    per_layer_dead_mass_g_m2: tuple[float, ...]
