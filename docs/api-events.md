# Simulation Event API Reference

The AgroGame API exposes simulation events in two places:

- **`PatchDayResponse.events`** — events from the most recent day step
- **`DailySnapshot.events`** — per-day events when stepping multiple days

## Event Schema

Each event is a JSON object with three fields:

```json
{
  "event_type": "WaterInfiltrated",
  "module": "agrogame.soil.water.events",
  "data": { ... }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Event class name (see table below) |
| `module` | string | Python module path where the event is defined |
| `data` | object | Event-specific payload (varies by type) |

## Event Types Reference

### Water Cycle

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `WaterInfiltrated` | `layer_indices: int[]`, `amounts_mm: float[]` | Water entering soil layers from rainfall |
| `WaterDrained` | `from_layer: int`, `to_layer: int`, `amount_mm: float` | Percolation between layers |
| `RunoffGenerated` | `amount_mm: float`, `curve_number: float` | Surface runoff (SCS method) |
| `EvaporationTaken` | `amount_mm: float` | Soil surface evaporation |
| `TranspirationByLayer` | `layer_indices: int[]`, `amounts_mm: float[]`, `total_mm: float` | Root water uptake per layer |
| `CanopyIntercepted` | `amount_mm: float` | Rainfall intercepted by canopy |
| `CanopyEvaporated` | `amount_mm: float` | Evaporation from canopy surface |

### Nitrogen Cycle

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `NitrificationOccurred` | `layer: int`, `amount_kg_ha: float` | NH4 converted to NO3 |
| `MineralizationOccurred` | `layer: int`, `amount_kg_ha: float` | Organic N released as mineral N |
| `DenitrificationOccurred` | `layer: int`, `amount_kg_ha: float` | NO3 lost as N2 gas (anaerobic) |
| `VolatilizationOccurred` | `layer: int`, `amount_kg_ha: float` | NH3 lost to atmosphere |
| `NutrientLeached` | `nutrient: str`, `amount_kg_ha: float`, `layer: int` | Nutrient lost below root zone |

### Plant Growth

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `LightIntercepted` | `fraction: float`, `intercepted_par_mj_m2: float` | PAR captured by canopy |
| `BiomassAccumulated` | `increment_g_m2: float`, `total_g_m2: float` | Daily biomass production |
| `LAIUpdated` | `previous_lai: float`, `new_lai: float` | Leaf area change |
| `GddAccumulated` | `daily_gdd: float`, `total_gdd: float` | Growing degree-day accumulation |
| `StageChanged` | `from_stage: str`, `to_stage: str`, `at_gdd: float` | Phenology stage transition |
| `RootDepthChanged` | `previous_cm: float`, `new_cm: float` | Root penetration depth change |

### Plant Stress

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `WaterStressComputed` | `supply_mm: float`, `demand_mm: float`, `stress: float` | Water stress ratio (1=none, 0=severe) |
| `NutrientStressComputed` | `nutrient: str`, `uptake_kg_ha: float`, `demand_kg_ha: float`, `stress: float` | Nutrient limitation |

### Soil Biology

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `SOMDecomposed` | `layer: int`, `pool: str`, `decomposed_c_kg_ha: float` | Organic matter breakdown |
| `CO2Respired` | `layer: int`, `co2_c_kg_ha: float` | Microbial respiration |
| `MicrobialGrowth` | `layer: int`, `delta_c_kg_ha: float` | Microbial biomass increase |
| `MicrobialMortality` | `layer: int`, `c_to_som_kg_ha: float` | Microbial turnover |

### Soil Chemistry

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `SoilPHUpdated` | `layer: int`, `ph: float` | pH change from buffering |
| `PhosphorusFixationOccurred` | `layer: int`, `amount_fixed_kg_ha: float` | P locked into minerals |

## Usage in Godot Frontend

Events are available per-patch after each `/step` call:

```gdscript
# Single day step
var data: Dictionary = step_response
for patch: Dictionary in data["patches"]["f1"]:
    var events: Array = patch.get("events", [])
    for evt: Dictionary in events:
        match evt["event_type"]:
            "WaterInfiltrated":
                # Animate water flowing into soil layers
                var layers: Array = evt["data"]["layer_indices"]
                var amounts: Array = evt["data"]["amounts_mm"]
            "TranspirationByLayer":
                # Show root water uptake arrows
                var total: float = evt["data"]["total_mm"]

# Multi-day step — events per day in daily_snapshots
for snap: Dictionary in data["daily_snapshots"]:
    var day_events: Array = snap.get("events", [])
```

## Multi-day Event Duplication

When stepping multiple days (`days > 1`), the **last day's events** appear in
both `patches[field_id][].events` and the final entry of `daily_snapshots[].events`.
This is by design — `patches` always reflects the most recent day, while
`daily_snapshots` gives per-day history. Frontend consumers should use one
source, not both, to avoid double-counting the final day.

## Filtering Tips

- **Water flow visualization**: filter for `WaterInfiltrated`, `WaterDrained`, `TranspirationByLayer`, `EvaporationTaken`
- **Nutrient cycling**: filter for events from `agrogame.soil.nitrogen.events` module
- **Growth milestones**: filter for `StageChanged`, `LAIUpdated`
- **Stress indicators**: filter for `WaterStressComputed`, `NutrientStressComputed`

## Notes

- Events are cleared at the start of each day step — each day's events are independent
- Event `data` always contains a `timestamp` field (ISO datetime string)
- All numeric values use metric units (mm, g/m2, kg/ha, etc.)
- Events are emitted in simulation order within each day
