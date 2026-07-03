from __future__ import annotations

from dataclasses import dataclass
from agrogame.events import BaseEvent


@dataclass(frozen=True)
class LightIntercepted(BaseEvent):
    fraction: float
    incident_par_mj_m2: float
    intercepted_par_mj_m2: float


@dataclass(frozen=True)
class BiomassAccumulated(BaseEvent):
    increment_g_m2: float  # shoot share added to canopy biomass this day
    total_g_m2: float  # cumulative shoot (canopy) biomass
    # Below-ground share of the same finite assimilate pool routed to roots
    # (#337). Total new plant tissue this day = increment_g_m2 + this.
    root_increment_g_m2: float = 0.0


@dataclass(frozen=True)
class LAIUpdated(BaseEvent):
    previous_lai: float
    new_lai: float


@dataclass(frozen=True)
class CanopyIntercepted(BaseEvent):
    """Rainfall intercepted by the canopy (mm)."""

    amount_mm: float


@dataclass(frozen=True)
class CanopyEvaporated(BaseEvent):
    """Water evaporated from the canopy store (mm)."""

    amount_mm: float


@dataclass(frozen=True)
class Harvested(BaseEvent):
    """Harvest applied to the canopy.

    fraction_remaining: Fraction of LAI (and optionally biomass) left after harvest.
    """

    fraction_remaining: float = 0.1


@dataclass(frozen=True)
class FrostDamageApplied(BaseEvent):
    """Frost caused LAI and biomass loss."""

    lai_loss: float
    biomass_loss_g_m2: float
    tmin_c: float
    severity: float


@dataclass(frozen=True)
class HeatDamageApplied(BaseEvent):
    """Heat stress reduced grain allocation."""

    grain_reduction_factor: float
    tmax_c: float


@dataclass(frozen=True)
class GrainNumberSet(BaseEvent):
    """Potential grain number frozen at the close of the critical window (#321).

    Diagnostic emitted once per season when the sink-source model fixes the
    grain number from peri-anthesis assimilate supply. Kernel weight during
    the subsequent fill phase equals grain_biomass / grain_number.
    """

    grain_number: float
    window_source_g_m2: float
    at_gdd: float
