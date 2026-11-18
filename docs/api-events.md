# Simulation Event API Reference

The AgroGame API exposes simulation events in two places:

- **`PatchDayResponse.events`** — events from the most recent day step
- **`DailySnapshot.events`** — per-day events when stepping multiple days

## Event Schema

Each event is a JSON object with three fields. This one is from a real `/step`
response:

```json
{
  "event_type": "WaterInfiltrated",
  "module": "agrogame.soil.water.events",
  "data": {"layer_indices": [0], "amounts_mm": [4.167671291363939]}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Event class name (see table below) |
| `module` | string | Python module path where the event is defined |
| `data` | object | The event's dataclass fields, one key each (varies by type) |

Each patch's `EventRecorder` subscribes to `BaseEvent`, so every event emitted
on the patch's bus reaches `/step`, `*Computed` diagnostics included; no type
is opted in. How `data` values are encoded (records, dates, enums, no
wall-clock `timestamp`) is specified once, in
[API § Event payloads](api.md#event-payloads-562).

## Event Types Reference

### Simulation Clock

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `DayTick` | `sim_date: str` (ISO date), `phase: str`, `drivers: object \| null`, `target_ph`, `tmin_c`, `tmax_c` (°C), `shortwave_mj_m2` (MJ m⁻² d⁻¹), `plant_n_demand_kg_ha`, `plant_p_demand_kg_ha`, `plant_s_demand_kg_ha`: `float \| null` | The day's clock and drivers, once per phase (`day_start` … `day_end`). `drivers` is set on the `water` and `et` phases only: `{rainfall_mm, irrigation_mm, evaporation_mm: float (mm), rainfall_intensity_mm_hr: float \| null (mm/hr)}`. `/step` sets only `rainfall_mm`, the day's precipitation; irrigation arrives through the `irrigate` action, so the others are 0.0 and `null` |

### Water Cycle

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `WaterInfiltrated` | `layer_indices: int[]`, `amounts_mm: float[]` | Water entering soil layers from rainfall |
| `WaterDrained` | `from_layer: int`, `to_layer: int`, `amount_mm: float` | Percolation between layers |
| `RunoffGenerated` | `amount_mm: float`, `curve_number: int` | Surface runoff (SCS method) |
| `EvaporationTaken` | `amount_mm: float` | Soil surface evaporation |
| `TranspirationByLayer` | `layer_indices: int[]`, `amounts_mm: float[]`, `total_mm: float` | Root water uptake per layer |
| `CanopyIntercepted` | `amount_mm: float` | Rainfall intercepted by canopy |
| `CanopyEvaporated` | `amount_mm: float` | Evaporation from canopy surface |
| `EvapotranspirationComputed` | `et0_mm`, `evaporation_mm`, `transpiration_mm`: `float` (mm) | Diagnostic: the day's reference ET0 and actual soil evaporation and transpiration, once per day ([fields](#evapotranspirationcomputed)) |

#### `EvapotranspirationComputed`

A diagnostic (`*Computed`, see [conventions](conventions.md)): `ETRuntime`
emits it once per patch per simulated day on the `et` phase, and it drives no
state. A real `/step` event (maize on `loam_temperate`, `netherlands_temperate`,
seed 42, day 40, 2024-05-10); values are sent unrounded:

```json
{
  "event_type": "EvapotranspirationComputed",
  "module": "agrogame.atmosphere.et.events",
  "data": {
    "et0_mm": 3.858278176723572,
    "evaporation_mm": 1.5737359349491402,
    "transpiration_mm": 1.264908793959829
  }
}
```

| Field | Unit | Meaning |
|-------|------|---------|
| `et0_mm` | mm d⁻¹ | Reference evapotranspiration ET0, the evaporative demand of the FAO-56 reference grass surface (Allen et al. 1998). Computed by Priestley–Taylor (Priestley & Taylor 1972; α = 1.26, `EtParams.pt_alpha`) from mean air temperature and net radiation Rn = 0.6·Rs (ADR-014; FAO-56 Eqs. 38–40), not by the FAO-56 Penman–Monteith Eq. 6, so it has no wind or vapour-pressure-deficit term. It does not depend on the crop. |
| `evaporation_mm` | mm d⁻¹ | Actual soil evaporation E. Its potential is the share of ET0 the canopy does not cover, ET0·exp(−k·LAI) with k = 0.6 (`EtParams.extinction_coefficient_k`), limited by Ritchie (1972) two-stage drying, surface residue and the topsoil water above wilting point. FAO-56 counterpart: Ke·ET0 (Eq. 69). Equals the day's `EvaporationTaken.amount_mm`. |
| `transpiration_mm` | mm d⁻¹ | Actual crop transpiration T: root uptake across the rooted layers toward the potential Tp = ET0·(1 − exp(−k·LAI)), never above it. FAO-56 counterpart: Ks·Kcb·ET0 (Eq. 80). Equals the day's `TranspirationByLayer.total_mm` and `WaterStressComputed.supply_mm`, whose `demand_mm` is Tp. |

`evaporation_mm + transpiration_mm` is the day's actual crop
evapotranspiration, the model's counterpart of FAO-56's
ETc adj = (Ks·Kcb + Ke)·ET0 (Eq. 80). The engine partitions ET0 by canopy
cover rather than by crop coefficients, so no Kc or Kcb appears in the
payload.

### Nitrogen Cycle

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `NitrificationOccurred` | `layer: int`, `amount_kg_ha: float` | NH4 converted to NO3 |
| `MineralizationOccurred` | `layer: int`, `amount_kg_ha: float` | Organic N released as mineral N |
| `DenitrificationOccurred` | `layer: int`, `amount_kg_ha: float` | NO3 lost as N2 gas (anaerobic) |
| `VolatilizationOccurred` | `layer: int`, `amount_kg_ha: float` | NH3 lost to atmosphere |
| `NutrientLeached` | `nutrient: str`, `amount_kg_ha: float`, `layer: int` | Nutrient lost below root zone |
| `MassFlowNSupplyComputed` | `total_kg_ha: float`, `by_layer: float[]` (kg/ha, one per layer) | Diagnostic: potential NO3 supply to roots by transpiration mass flow; neither debited from the soil nor credited to the plant |

### Plant Growth

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `LightIntercepted` | `fraction: float`, `intercepted_par_mj_m2: float` | PAR captured by canopy |
| `BiomassAccumulated` | `increment_g_m2: float`, `total_g_m2: float` | Daily biomass production |
| `LAIUpdated` | `previous_lai: float`, `new_lai: float` | Leaf area change |
| `GddAccumulated` | `daily_gdd: float`, `total_gdd: float` | Growing degree-day accumulation |
| `StageChanged` | `from_stage: str`, `to_stage: str`, `at_gdd: float` | Phenology stage transition; stages are `planted`, `emerged`, `vegetative`, `flowering`, `grain_fill`, `maturity`, as in `crop_stage` |
| `RootDepthChanged` | `previous_cm: float`, `new_cm: float` | Root penetration depth change |

### Plant Stress and Damage

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `WaterStressComputed` | `supply_mm: float`, `demand_mm: float`, `stress: float` | Water stress ratio (1=none, 0=severe) |
| `NutrientStressComputed` | `nutrient: str`, `uptake_kg_ha: float`, `demand_kg_ha: float`, `stress: float` | Nutrient limitation |
| `PlantNUptakeComputed` | `uptake_kg_ha: float`, `demand_kg_ha: float` (kg N/ha) | Diagnostic: the day's soil N uptake and demand, handed to whole-shoot plant-N accounting (#360) |
| `FrostDamageApplied` | `lai_loss: float` (m²/m²), `biomass_loss_g_m2: float`, `tmin_c: float` (°C), `severity: float` (0–1) | Frost cut leaf area and biomass |
| `HeatDamageApplied` | `grain_reduction_factor: float`, `tmax_c: float` (°C) | Heat above the crop's threshold at flowering or grain fill; that day's grain growth is multiplied by `grain_reduction_factor`. There is no `severity` field; the client derives one ([below](#what-the-godot-client-reads)) |
| `WaterloggingDetected` | `layer: int`, `theta: float`, `saturation: float` (m³/m³) | Top layer at or above 95 % of saturation, on each such day |

### Soil Biology

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `SOMDecomposed` | `layer: int`, `pool: str`, `decomposed_c_kg_ha: float` | Organic matter breakdown |
| `CO2Respired` | `layer: int`, `co2_c_kg_ha: float` | Microbial respiration |
| `MicrobialGrowthOccurred` | `layer: int`, `delta_c_kg_ha: float` | Microbial biomass increase |
| `MicrobialMortalityOccurred` | `layer: int`, `c_to_som_kg_ha: float` | Microbial turnover |
| `MicrobialActivityComputed` | `layer: int`, `activity_index: float`, `wfps: float` (0–1), `ph: float`, `temperature_c: float` (°C) | Diagnostic: a layer's microbial activity index and the moisture, pH and temperature it was computed from |
| `EnzymeGroupTotalsComputed` | `totals_c_kg_ha_by_group: object` (group → kg C/ha) | Diagnostic: the day's profile-wide enzyme production cost per enzyme group |

### Soil Chemistry

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `SoilPHUpdated` | `layer: int`, `ph: float` | pH change from buffering |
| `PhosphorusFixationOccurred` | `layer: int`, `amount_fixed_kg_ha: float` | P locked into minerals |

### Soil Gas and Redox

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `RedoxChanged` | `layer: int`, `eh_mv: float` (mV), `dominant_acceptor: str` | A layer's redox potential Eh, once per layer per day |
| `N2OEmitted` | `layer: int`, `amount_kg_n_ha: float` (N2O-N), `n2_amount_kg_n_ha: float` (N2-N), kg N/ha | Gaseous N from denitrification |
| `CH4Emitted` | `layer: int`, `amount_kg_c_ha: float` (kg CH4-C/ha) | Methane produced under strongly reducing conditions |
| `CH4Oxidized` | `layer: int`, `amount_kg_c_ha: float` (kg CH4-C/ha) | Methane oxidised in an aerobic layer |

### Soil Structure

| Event | Key Fields | Description |
|-------|-----------|-------------|
| `AggregateStructureUpdated` | `layer: int`, `micro`, `meso`, `macro: float` (fractions summing to 1), `mwd_mm: float` (mm) | A layer's aggregate size distribution and mean weight diameter |
| `TillageApplied` | `intensity: float` (0–1), `macro_destroyed_frac: float` (0–1) | Tillage broke up macroaggregates |
| `PoreNetworkComputed` | `layer: int`, `macro`, `meso`, `micro`, `crypto: float` (m³/m³, summing to the layer's porosity), `connectivity: float` (0–1) | Diagnostic: a layer's pore-size distribution, derived from texture and aggregation |

### Every Other Type

The tables above cover every `*Computed` diagnostic, every type the client
reads and the main flows; they are not the full list. Every type that reaches
`/step` is a frozen dataclass in the module its `module` names
(`agrogame.soil.biopores.events` is `agrogame/soil/biopores/events.py`), and
its fields are exactly the `data` keys. That source is the complete list:
`tests/unit/test_api_event_serialisation.py` discovers every `BaseEvent`
subclass under `agrogame` and checks each serialises through `/step` with
those keys. `event_type` alone is not unique: `CanopyIntercepted` and
`CanopyEvaporated` are each defined in both `agrogame.soil.canopy.events` and
`agrogame.soil.water.events`, and `module` tells them apart.

## What the Godot Client Reads

The client reads events only from `patches[field_id][i].events`, the last
stepped day; it ignores `daily_snapshots[].events`. These are the only types
and `data` fields it reads. It does not read `EvapotranspirationComputed`.

| Event | `data` fields read | Script | Drives |
|-------|--------------------|--------|--------|
| `NutrientStressComputed` | `nutrient`, `stress`, `uptake_kg_ha` | `farm_tiles.gd`, `stress_icons.gd`, `flow_overlay.gd` | Crop stress visuals, deficiency icons (`stress` < 0.5), N and P uptake tubes |
| `WaterStressComputed` | `stress` | `stress_icons.gd` | Drought icon (`stress` < 0.5) |
| `FrostDamageApplied` | `severity` | `farm_tiles.gd`, `stress_icons.gd` | Crop frost visuals and icon |
| `HeatDamageApplied` | `grain_reduction_factor`: severity is `1 − grain_reduction_factor`, the share of that day's grain growth lost, clamped to [0, 1] (#569). If the field is missing, the client logs a warning and uses 0.5 | `farm_tiles.gd`, `stress_icons.gd` | Crop heat visuals and icon |
| `WaterloggingDetected` | none; its presence shows the icon | `stress_icons.gd` | Waterlogging icon |
| `RedoxChanged` | `eh_mv` | `stress_icons.gd` | Anaerobic icon (`eh_mv` < −100) |
| `WaterInfiltrated` | `amounts_mm` (summed), `layer_indices` | `flow_overlay.gd` | Infiltration tubes, rain connector, pulse above 5 mm |
| `WaterDrained` | `amount_mm`, `from_layer`, `to_layer` | `flow_overlay.gd` | Drainage tubes |
| `TranspirationByLayer` | `total_mm`, `layer_indices` | `flow_overlay.gd` | Transpiration tube |
| `EvaporationTaken`, `RunoffGenerated` | `amount_mm` | `flow_overlay.gd` | Evaporation and runoff tubes |
| `NitrificationOccurred`, `MineralizationOccurred`, `DenitrificationOccurred`, `VolatilizationOccurred`, `NutrientLeached` | `amount_kg_ha`, `layer` | `flow_overlay.gd` | Nitrogen tubes |
| `PhosphorusFixationOccurred` | `amount_fixed_kg_ha`, `layer` | `flow_overlay.gd` | P fixation tube |
| `SOMDecomposed` | `decomposed_c_kg_ha`, `layer` | `flow_overlay.gd` | Decomposition tube |
| `CO2Respired` | `co2_c_kg_ha`, `layer` | `flow_overlay.gd` | Respiration tube |
| `N2OEmitted` | `amount_kg_n_ha`, `layer` | `flow_overlay.gd` | N2O tube |
| `CH4Emitted`, `CH4Oxidized` | `amount_kg_c_ha`, `layer` | `flow_overlay.gd` | Methane tubes |
| `TillageApplied` | `macro_destroyed_frac` | `flow_overlay.gd` | Tillage tube |
| `AggregateStructureUpdated` | `mwd_mm`, `layer` | `flow_overlay.gd` | Aggregation tube |

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
- All numeric values use metric units (mm, g/m2, kg/ha, etc.)
- Events are emitted in simulation order within each day
