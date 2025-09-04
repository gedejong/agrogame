## Event-driven Orchestrator with Builder and Calendar

This document proposes a refactor to achieve strict separation of concerns (SoC) using an event-driven architecture with a Calendar scheduler and a builder-based orchestrator wiring.

### Goals

- Modules are decoupled; they only know about the `EventBus` and their own ports.
- The orchestrator wires modules together (construction-time only) without peeking into internals.
- Daily progression is driven by a `Calendar` emitting phased `DayTick` events (weather → chemistry → water → plant structure → ET → nutrients → canopy → day_end).
- Deterministic ordering while keeping modules independent and testable in isolation.

### Core Concepts

- **Builder Orchestrator**: A thin `SimulationBuilder` constructs modules, injects the shared `EventBus`, and returns an `App` object exposing `calendar.tick(...)` as the only runtime entry point.
- **Calendar**: Emits `DayTick` events with the current date, optional `DailyDrivers`, and optional targets (e.g., `target_ph`). Phases encode ordering. Modules subscribe and act on their relevant phases.
- **Ports**: Modules expose small, typed ports where needed (e.g., ET consumes a `WaterProfile`, `WaterState`, `WaterActuator`) but are obtained at build time and not touched by the orchestrator during the run.

### Daily Phase Order (initial)

1. weather: produce `WeatherUpdated` with temperature, radiation, rainfall
2. chemistry: buffer pH (`SoilPHUpdated` events)
3. water: update storages; emit `WaterDrained`, `TranspirationByLayer`
4. plant_structure: roots/phenology state transitions; emit `RootDistributionUpdated`
5. et: compute ET, drive water extraction via water actuator; emit ET diagnostics
6. nutrients: nitrogen, phosphorus daily steps (consume cached pH, root fractions)
7. canopy: growth/photosynthesis; emit canopy events
8. day_end: finalize/record

### Orchestrator Builder (sketch)

```python
class SimulationApp:
    def __init__(self, event_bus: EventBus, calendar: Calendar):
        self.event_bus = event_bus
        self.calendar = calendar

class SimulationBuilder:
    def __init__(self) -> None:
        self._event_bus = EventBus()

    def build(self, profile: SoilProfile) -> SimulationApp:
        # Construct modules with shared bus; wire ports at construction
        water_model = CascadingBucketWaterModel(event_bus=self._event_bus)
        water_state = SoilWaterState(profile)
        chem = SoilChemistryModule(self._event_bus, n_layers=len(profile.layers))
        n_state = SoilNitrogenState(profile)
        n_cycle = NitrogenCycle(self._event_bus, n_state, water_state=water_state, profile=profile)
        p_state = SoilPhosphorusState(profile)
        p_cycle = PhosphorusCycle(self._event_bus, p_state, water_state=water_state, profile=profile)
        phen = PhenologyModule(..., event_bus=self._event_bus)
        canopy = CanopyModule(..., event_bus=self._event_bus)
        roots = RootModule(..., event_bus=self._event_bus)
        et = Evapotranspiration(EtParams())
        # Calendar last
        calendar = Calendar(self._event_bus)
        return SimulationApp(self._event_bus, calendar)
```

### Module Responsibilities

- Subscribe to `DayTick` and perform work only in their respective phases.
- Emit domain events (e.g., `SoilPHUpdated`, `WaterDrained`, `NutrientLeached`).
- Never call other modules directly; rely on events and ports injected at construction.

### Migration Plan

1. Introduce `Calendar` and `DayTick` (done).
2. Add `SimulationBuilder` returning `SimulationApp` (thin wrapper replacing direct methods on orchestrator).
3. Move daily logic out of `FullSimulationOrchestrator.step_day` into module handlers responding to `DayTick` phases:
   - Chemistry (done) → run buffering on `chemistry`.
   - Water → update storages on `water`.
   - Roots/Phenology → `plant_structure`.
   - ET → compute and actuate on `et`.
   - Nutrients → run `daily_step` on `nutrients` (consuming cached pH and root fractions).
   - Canopy → growth on `canopy`.
4. Replace `FullSimulationOrchestrator` with `SimulationBuilder` + `SimulationApp`.
5. Tests: phase ordering, module event interactions, and end-to-end scenario via `calendar.tick`.

### Benefits

- Orchestrator no longer knows about layers, ET algorithms, or internal states.
- Deterministic and extensible scheduling.
- Easier simulation control (e.g., mid-season interventions via events).


