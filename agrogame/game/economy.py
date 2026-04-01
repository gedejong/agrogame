"""Economic ledger with costs, revenue, and season-end settlement.

Implements the economic model from ADR-003: static price tables, credits
currency, per-event cost tracking, and season-end profit calculation.
The simulation engine does not know about money — this module is called
by the game loop / API layer via composition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CostEntry:
    """A single cost event recorded in the ledger."""

    day: int
    category: str  # seed, fertilizer, irrigation, labor, equipment
    description: str
    amount_credits: int


@dataclass(frozen=True)
class CropPrice:
    """Base price and seasonal multipliers for one crop."""

    base_credits_per_kg: float
    seasonal_multipliers: list[float]  # Q1, Q2, Q3, Q4


@dataclass
class PriceTable:
    """Static price tables for inputs and crop revenue."""

    input_costs: dict[str, float]  # category → credits per unit
    crop_prices: dict[str, CropPrice]  # crop key → CropPrice

    @classmethod
    def load(cls, path: Path | None = None) -> PriceTable:
        """Load price table from YAML."""
        import yaml

        if path is None:
            path = Path("data/economy/prices.yaml")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        input_costs = {k: float(v) for k, v in data.get("input_costs", {}).items()}
        crop_prices: dict[str, CropPrice] = {}
        for key, raw in data.get("crop_prices", {}).items():
            crop_prices[key] = CropPrice(
                base_credits_per_kg=float(raw["base_credits_per_kg"]),
                seasonal_multipliers=[
                    float(m) for m in raw.get("seasonal_multipliers", [1, 1, 1, 1])
                ],
            )
        return cls(input_costs=input_costs, crop_prices=crop_prices)

    def get_crop_price(self, crop_key: str, quarter: int = 1) -> float:
        """Get effective price (base * seasonal multiplier) for a crop."""
        cp = self.crop_prices.get(crop_key)
        if cp is None:
            return 0.0
        qi = max(0, min(3, quarter - 1))
        mult = cp.seasonal_multipliers[qi] if cp.seasonal_multipliers else 1.0
        return cp.base_credits_per_kg * mult


@dataclass
class EconomicLedger:
    """Tracks credits, costs, and revenue across seasons.

    The simulation engine does not touch this. The game loop calls
    record_cost() when applying management actions, and settle_season()
    after harvest.
    """

    balance_credits: int = 10000  # starting capital
    costs: list[CostEntry] = field(default_factory=list)
    season_revenue: int = 0
    season_costs: int = 0
    season_profit: int = 0

    def record_cost(
        self,
        day: int,
        category: str,
        description: str,
        amount_credits: int,
    ) -> None:
        """Record a cost event and immediately deduct from balance."""
        if amount_credits <= 0:
            return
        self.costs.append(
            CostEntry(
                day=day,
                category=category,
                description=description,
                amount_credits=amount_credits,
            )
        )
        self.season_costs += amount_credits
        self.balance_credits -= amount_credits

    def settle_season(
        self,
        grain_g_m2: float,
        crop_key: str,
        prices: PriceTable,
        quarter: int = 3,
        area_ha: float = 1.0,
    ) -> int:
        """Calculate revenue, compute profit, update balance.

        Args:
            grain_g_m2: Grain biomass from simulation (g/m2).
            crop_key: Crop preset key for price lookup.
            prices: Price table with crop prices.
            quarter: Season quarter (1-4) for seasonal multiplier.
            area_ha: Field area in hectares.

        Returns:
            Season profit (can be negative).
        """
        # grain_g_m2 * 10 = kg/ha (100 g/m2 = 1 t/ha = 1000 kg/ha)
        kg_per_ha = grain_g_m2 * 10.0
        price_per_kg = prices.get_crop_price(crop_key, quarter)
        revenue = int(kg_per_ha * area_ha * price_per_kg)

        self.season_revenue = revenue
        self.season_profit = revenue - self.season_costs
        # Costs already deducted in record_cost(); only add revenue here.
        self.balance_credits += revenue
        return self.season_profit

    def reset_season(self) -> None:
        """Clear season-level tracking for the next season."""
        self.costs.clear()
        self.season_revenue = 0
        self.season_costs = 0
        self.season_profit = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for save/load."""
        return {
            "balance_credits": self.balance_credits,
            "costs": [
                {
                    "day": c.day,
                    "category": c.category,
                    "description": c.description,
                    "amount_credits": c.amount_credits,
                }
                for c in self.costs
            ],
            "season_revenue": self.season_revenue,
            "season_costs": self.season_costs,
            "season_profit": self.season_profit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EconomicLedger:
        """Restore from save data."""
        ledger = cls(
            balance_credits=int(data["balance_credits"]),
            season_revenue=int(data.get("season_revenue", 0)),
            season_costs=int(data.get("season_costs", 0)),
            season_profit=int(data.get("season_profit", 0)),
        )
        for c in data.get("costs", []):
            ledger.costs.append(
                CostEntry(
                    day=int(c["day"]),
                    category=str(c["category"]),
                    description=str(c["description"]),
                    amount_credits=int(c["amount_credits"]),
                )
            )
        return ledger
