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


@dataclass(frozen=True)
class EnzymeGroupTotals(BaseEvent):
    """Profile-wide enzyme production cost totals by group for a day."""

    totals_c_kg_ha_by_group: Dict[str, float]


@dataclass(frozen=True)
class SubstrateAvailable(BaseEvent):
    """SOM-derived substrate availability for a soil layer (per day).

    available_c_kg_ha: labile carbon available to microbes today.
    quality_index: optional quality factor (0..1) indicating ease of use.
    """

    layer: int
    available_c_kg_ha: float
    quality_index: float


@dataclass(frozen=True)
class RhizospherePrimingPulse(BaseEvent):
    """Priming multiplier for a soil layer due to root exudates.

    multiplier: 1.0 baseline, >1 boosts activity/substrate use transiently.
    """

    layer: int
    multiplier: float
