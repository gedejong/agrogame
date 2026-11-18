---
module: agrogame.events
doc_type: module
references:
  - "Hohpe & Woolf, Enterprise Integration Patterns (2003) — observer/pub-sub"
key_classes: [BaseEvent, EventBus, EventHandlerError]
key_events: []
primary_tests:
  - tests/test_event_bus.py
  - tests/test_events.py
related_adrs: [ADR-002]
---

## Events & Debugging

This project uses an event-driven architecture built on `agrogame.events.EventBus` and `BaseEvent`.

### Handler exceptions (#606)

Every exception a handler raises propagates out of `EventBus.emit` as
`EventHandlerError`, a `RuntimeError` subclass. Its `handler` is the handler's
`module.qualname` (its `repr` when it has none), its `event_type` is the
event's class name, and the handler's own exception is its `__cause__`.
Delivery stops at the failing handler: later subscribers to that event, and
the `BaseEvent` catch-alls after a failing exact-type handler, are not called.
When a handler fails inside a nested `emit`, the error names that innermost
handler and its event, not the outer handler that emitted.

No subscriber is isolated. The bus used to log handler exceptions at DEBUG and
carry on, so a crashing simulation handler silently dropped that day's
physics. An observer that genuinely needs isolation needs its own issue, and
must log its failures at WARNING or above, naming the event type. The API maps
the error to a 500 ([API](api.md), "Simulation errors").

### EventRecorder

`EventRecorder` subscribes to `BaseEvent` and captures a lightweight log for visualization. It records:

- `day_index`: integer day context (set via `rec.set_day(day)` in simulation loops)
- `event_type`: dataclass name
- `module_name`: Python module of the event (used for bucketing)
- `data`: serialized dataclass fields from `BaseEvent.to_dict()`

### Visualizations

- `scripts/plot_events_timeline.py`: daily swimlanes (driven by `Calendar` ticks)
- `scripts/plot_events_heatmap.py`: daily event density per module (uses the shared `EventBus` with `Calendar`)
- `scripts/plot_events_dependencies.py`: circular dependency from same-day transitions (now uses `FullSimulationOrchestrator` and `DayTick` to stage updates)

Common flags:

- `--include Soil,ET` limit to specific buckets
- `--exclude Weather` hide a bucket
- `--grep Transpir` filter on event type substring (case-insensitive)
- `--csv-out out/events.csv` export data for further analysis

Example (Calendar-driven):

```bash
poetry run python scripts/plot_events_timeline.py \
  --days 120 --include Soil,ET,Nitrogen \
  --grep Transpir --csv-out out/events_timeline.csv
```

### Notes

- The dependency graph supports `--fc-scale` to alter field capacity globally when you want to drive more water (and nitrogen leaching) events.
- All scripts use Groningen weather defaults and sanitized inputs; real datasets can be used via `--weather-file` or NASA POWER flags.


