# Water Model Abstraction and Events

- Interface: `SoilWaterModel.update_daily(profile, state, drivers) -> WaterFluxes`
- Default impl: `CascadingBucketWaterModel`
- Water-only events via `EventBus`: `WaterInfiltrated`, `WaterDrained`, `RunoffGenerated`, `EvaporationTaken`, `TranspirationByLayer`
- Orchestrator owns state; other modules subscribe to water events
- ET integration uses ports (see Ports & Events) instead of direct soil imports
