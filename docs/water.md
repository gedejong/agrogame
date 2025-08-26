Water module summary

- EventBus: synchronous in-process pub/sub (`agrogame/soil/water/event_bus.py`)
- Events: `WaterInfiltrated`, `WaterDrained`, `RunoffGenerated`, `EvaporationTaken`
- Purpose: allow nutrients and plants to react to water movement

Key API
- `EventBus.subscribe(Event, handler)`
- `EventBus.emit(instance)`


