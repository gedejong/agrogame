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
