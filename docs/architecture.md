Architecture (compressed)

Modules
- Water: emits hydrological events via `EventBus`
- Nitrogen: subscribes to water, transforms N pools, emits N events
- Phenology: accumulates GDD, emits stage events
- Canopy: uses phenology, computes interception/biomass/LAI, emits canopy events

Patterns
- Event-driven coupling through `EventBus` (sync, in-process)
- State objects per subsystem; daily_step methods for updates


