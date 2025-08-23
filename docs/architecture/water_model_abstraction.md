# Water Model Abstraction and Events

- Interface: SoilWaterModel.update_daily(profile, state, drivers) -> WaterFluxes (immutable)
- Default impl: CascadingBucketWaterModel
- EventBus: synchronous, water-only events (WaterInfiltrated, WaterDrained, RunoffGenerated, EvaporationTaken)
- Orchestrator owns state; modules emit events; nutrients subscribe later.
