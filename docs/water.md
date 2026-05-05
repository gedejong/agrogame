---
module: agrogame.soil.water
doc_type: module
references:
  - "FAO-56 (Allen et al. 1998), §3 — reference ET and soil water balance"
  - "DSSAT v4.8 manual ch. 3 — cascading bucket layer model"
  - "USDA SCS curve-number runoff method"
  - "Dexter 2004 — aggregation effect on ksat"
key_classes:
  - CascadingBucketWaterModel
  - DualPorosityWaterModel
  - DualPorosityParams
  - SoilWaterBalance
  - SoilWaterState
  - DailyDrivers
  - WaterFluxes
key_events:
  - WaterInfiltrated
  - WaterDrained
  - RunoffGenerated
  - EvaporationTaken
  - PreferentialFlowOccurred
primary_tests:
  - tests/test_soil_water.py
  - tests/test_water_root_integration.py
  - tests/integration/test_realism.py::test_water_balance
related_adrs: [ADR-002, ADR-006]
---

Water module summary

- EventBus: synchronous in-process pub/sub (`agrogame/events/bus.py`)
- Events: `WaterInfiltrated`, `WaterDrained`, `RunoffGenerated`, `EvaporationTaken`
- Purpose: allow nutrients and plants to react to water movement

Key API
- `EventBus.subscribe(Event, handler)`
- `EventBus.emit(instance)`


