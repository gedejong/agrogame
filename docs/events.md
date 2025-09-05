## Events & Debugging

This project uses an event-driven architecture built on `agrogame.events.EventBus` and `BaseEvent`.

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


