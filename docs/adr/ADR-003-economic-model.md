# ADR-003: Economic Model Scope

## Status: Proposed

## Context

The science engine simulates soil-plant-atmosphere processes with high fidelity (7 crops, 3 climates, 3-pool SOM, validated water/nitrogen/phosphorus cycles), but has no concept of money. Every management action -- irrigation, fertilization, planting, harvesting -- is free and unconstrained.

Without costs and revenue, players have no reason to optimize. Irrigation is always maximal. Fertilizer is always applied at agronomic maximum. Crop rotation has no economic tradeoff against monoculture. The simulation is scientifically interesting but not a game.

We need an economic model that makes player decisions meaningful without requiring a full market simulation. V1 should be simple enough to implement in one sprint, transparent enough for players to reason about, and extensible enough to add complexity later.

## Decision

**Static price tables with seasonal multipliers. Generic "credits" currency. No real-time market simulation.**

### Input costs (per application)

| Input | Unit | Base cost (credits) |
|-------|------|-------------------|
| Seed (per crop) | per ha | 200-600 (crop-dependent) |
| Urea (46-0-0) | per kg N | 1.2 |
| Ammonium nitrate (34-0-0) | per kg N | 1.5 |
| TSP (0-46-0) | per kg P | 2.0 |
| Irrigation | per mm per ha | 0.3 |
| Labor | per management action | 50 |
| Equipment rental | per mechanized action | 150 |

### Revenue

| Output | Unit | Base price (credits) |
|--------|------|---------------------|
| Grain yield | per kg per ha | Crop-dependent (see below) |
| Straw/residue | per kg per ha | 0.05 (optional harvest) |

Crop base prices (credits/kg): wheat 0.25, maize 0.22, rice 0.30, soybean 0.35, potato 0.15, sorghum 0.20, barley 0.23.

### Seasonal multipliers

Each crop has a `price_seasonality` curve defined as 4 quarterly multipliers (Q1-Q4). Selling immediately at harvest uses the harvest-quarter multiplier. Storage (future feature) allows selling in a later quarter at that quarter's multiplier, but incurs a storage cost.

Example for wheat: `[1.1, 0.9, 0.85, 1.15]` -- prices are higher in Q1 (pre-harvest scarcity) and Q4 (export demand), lower in Q2-Q3 (harvest glut).

### Settlement

Economy settles at the end of each season (not daily). When a field is harvested:

1. Revenue = yield_kg_per_ha x area_ha x base_price x seasonal_multiplier
2. Total costs = sum of all input costs incurred during the season for that field
3. Profit = revenue - total costs
4. Player credit balance updated

This aligns with ADR-004 (season-turn settlement) and keeps the economic loop simple: plant, manage, harvest, settle, repeat.

### Currency

Generic "credits" with no real-world currency mapping. Avoids localization issues, exchange rate complexity, and the implication that the game models real commodity markets. Credits are integers (no fractional credits) to avoid floating-point display issues.

### Carbon credits (optional, V2)

Fields with positive soil organic carbon change over a season can claim carbon credits: 1 credit per tonne CO2-equivalent sequestered. This incentivizes cover crops, reduced tillage, and organic amendments. Deferred to V2 because it requires validated SOC change tracking, which depends on the 3-pool SOM model being well-calibrated.

### Implementation

A new `agrogame.economy` module with:

```python
@dataclass
class PriceTable:
    seed_costs: dict[str, float]        # crop_name -> credits/ha
    fertilizer_costs: dict[str, float]  # product_name -> credits/kg_nutrient
    irrigation_cost_per_mm_ha: float
    labor_cost_per_action: float
    equipment_cost_per_action: float
    crop_prices: dict[str, float]       # crop_name -> credits/kg
    seasonality: dict[str, list[float]] # crop_name -> [Q1, Q2, Q3, Q4]

@dataclass
class SeasonLedger:
    field_id: str
    season: int
    costs: list[CostEntry]
    revenue: float | None  # None until harvest
    profit: float | None

class EconomyManager:
    def record_cost(self, field_id: str, cost: CostEntry) -> None: ...
    def settle_harvest(self, field_id: str, yield_kg_ha: float, area_ha: float, quarter: int) -> float: ...
    def get_balance(self) -> int: ...
```

Cost recording hooks into existing management events via `EventBus`. When `IrrigationAppliedEvent` fires, `EconomyManager` records the cost. No changes to the science modules.

## Consequences

**Positive:**
- Players immediately face tradeoffs: "Is 20 mm extra irrigation worth 6 credits/ha when my wheat is already at 80% of potential yield?"
- Static prices are trivial to implement, balance-test, and explain to players. No hidden complexity.
- Cost recording via EventBus means zero coupling between economy and science modules. The economy module is a pure listener.
- Seasonal multipliers add just enough market flavor to reward timing decisions without requiring a market simulator.
- Integer credits avoid floating-point display weirdness (e.g., "You earned 1234.0000001 credits").

**Negative:**
- Static prices remove the "market risk" dimension of real farming. Players can calculate exact expected revenue before planting. This is a deliberate simplification for V1.
- Price tables need manual balancing. If wheat is too profitable relative to soybean, everyone grows wheat. Requires playtesting and iteration.
- No inflation, no interest rates, no loans. The economy is a simple ledger, not a financial simulation. Players who want depth may find it shallow.

## Alternatives Considered

**Dynamic market with supply/demand.** Prices adjust based on player production volume (single-player) or aggregate production (multiplayer). Adds realism but requires market equilibrium modeling, is hard to balance, and makes revenue unpredictable in ways that frustrate rather than challenge. Rejected for V1. Reconsidered for V2 multiplayer.

**Real-world currency (USD/EUR).** Anchors prices to reality but requires constant rebalancing as commodity markets move, introduces localization issues, and implies the game is an accurate economic simulator (it isn't). Rejected permanently.

**Daily settlement.** Costs and revenue calculated every day. Adds granularity but most farming economics are seasonal -- you don't sell grain daily. Overcomplicates the ledger and UI. Rejected.

**No economy (keep it a pure simulation).** Players already have the science engine for that. A game needs objectives, constraints, and consequences. Without money, there's no reason to choose soybean over wheat, or 60 mm irrigation over 100 mm. Rejected -- this ADR exists precisely because we need an economy to make the game a game.

**Stochastic price shocks.** Random events (drought elsewhere, export ban, pest outbreak) shift prices by +/- 20%. Adds excitement but makes the game feel unfair if a price crash wipes out a good season. Better suited as an optional "hard mode" difficulty setting in V2. Rejected for V1.
