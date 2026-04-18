"""Micronutrient domain events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class RedoxNutrientTransformed(BaseEvent):
    """Redox-driven transformation shifted a micronutrient pool (#216).

    Emitted by ``MicronutrientCycle.apply_redox_adjustment`` when Fe or
    Mn moves between sorbed/mineral (implicit: total − available) and
    available forms in response to a soil Eh change. Mass is conserved:
    ``total`` is unchanged, only the ``available`` split shifts.

    Attributes:
        layer: Zero-based soil layer index.
        element: Nutrient element code ("Fe" or "Mn").
        amount_ppm: Magnitude of the shift (ppm), always non-negative.
        direction: "reduction" (sorbed → available) or "oxidation"
            (available → sorbed).
    """

    layer: int
    element: str
    amount_ppm: float
    direction: str
