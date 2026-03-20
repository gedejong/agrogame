from __future__ import annotations

from dataclasses import dataclass
from agrogame.events import BaseEvent

from .types import BiomassAllocations, BiomassPools


@dataclass(frozen=True)
class BiomassPartitioned(BaseEvent):
    allocations: BiomassAllocations
    pools_after: BiomassPools
