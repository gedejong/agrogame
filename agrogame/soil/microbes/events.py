from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class MicrobialGrowth(BaseEvent):
    layer: int
    delta_c_kg_ha: float
    delta_n_kg_ha: float


@dataclass(frozen=True)
class MicrobialMortality(BaseEvent):
    layer: int
    c_to_som_kg_ha: float
    n_to_som_kg_ha: float


@dataclass(frozen=True)
class EnzymeProduced(BaseEvent):
    layer: int
    enzyme_group: str
    production_cost_c_kg_ha: float
    params: Dict[str, float]


@dataclass(frozen=True)
class MicrobialSnapshot(BaseEvent):
    """Daily snapshot for visualization convenience."""

    total_c_kg_ha: float
    total_n_kg_ha: float


@dataclass(frozen=True)
class MicrobialFBUpdated(BaseEvent):
    """Fungal:bacterial fraction updated for a soil layer."""

    layer: int
    fungal_fraction: float


@dataclass(frozen=True)
class MicrobialActivityComputed(BaseEvent):
    """Activity index computed for a soil layer given environment."""

    layer: int
    activity_index: float
    wfps: float
    ph: float
    temperature_c: float
