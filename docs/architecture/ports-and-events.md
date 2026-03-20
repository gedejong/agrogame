# Ports and Events Integration Pattern

This project uses a ports-and-events pattern to decouple domain modules while keeping integrations explicit and testable.

## ET ⇄ Water via Ports
- Ports live in `agrogame/atmosphere/et/ports.py`:
  - `WaterProfile`, `WaterState` (read/write water storage)
  - `TranspirationExtractor` and `EvaporationApplier` capabilities
  - `WaterActuator` combines the capabilities used by ET
- `Evapotranspiration.actual_et(...)` depends on the ports instead of concrete soil types and calls:
  - `water_model.apply_evaporation(...)` to remove topsoil water
  - `water_model.extract_transpiration_by_roots(...)` for plant uptake

## Water emits Events
- `CascadingBucketWaterModel` emits water-only events via `EventBus`:
  - `EvaporationTaken`, `TranspirationByLayer`, `WaterInfiltrated`, `WaterDrained`, `RunoffGenerated`
- Downstream modules (e.g., nutrients) subscribe to these events instead of reading state directly.

## Architectural Rules
- Import-linter contracts enforce:
  - `agrogame.atmosphere` independent of `agrogame.soil` (use ports)
  - `agrogame.weather` independent of domain modules
  - `agrogame.soil` must not import `agrogame.plant`

## Migration Notes
- Existing code using concrete soil types can remain; ports are duck-typed by those types.
- Prefer emitting/consuming events for cross-module coordination.
