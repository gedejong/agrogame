# ADR-001: Game State Format and Persistence

## Status: Proposed

## Context

The science engine already serializes soil state via `SoilSnapshot.to_dict()`/`from_dict()` for multi-season continuity. This covers water, nitrogen, phosphorus, microbial, SOM (3-pool), pH, and crop history -- but only for a single field's soil pools.

A playable game requires persisting the full game state: soil snapshots for N fields, player economy (credits, loans, revenue history), field metadata (location, area, soil profile reference, active crop), management plans (irrigation schedules, fertilizer applications), crop rotation history, and calendar/weather state. Players expect save/load with no data loss between sessions.

We need a single serialization format that is debuggable during development, extensible as new modules land, and forward-compatible so older saves don't break when we add economy or weather features.

## Decision

**Single JSON save file with a versioned, schema-validated format.**

The save file is a single `.agrosave.json` file containing:

```json
{
  "schema_version": 1,
  "saved_at": "2026-03-27T14:00:00Z",
  "game": {
    "day": 247,
    "season": 2,
    "credits": 12450,
    "climate_preset": "temperate"
  },
  "fields": [
    {
      "field_id": "field_01",
      "area_ha": 5.0,
      "soil_profile_key": "clay_loam_3layer",
      "active_crop": "winter_wheat",
      "soil_snapshot": { "...SoilSnapshot.to_dict() output..." },
      "root_state": {
        "current_depth_cm": 42.5,
        "distribution": "exponential",
        "layer_fractions": [0.6, 0.3, 0.1]
      },
      "management_plan": { "...ManagementPlan serialization..." },
      "crop_history": ["maize", "soybean"]
    }
  ],
  "economy": {
    "credit_balance": 12450,
    "revenue_history": [],
    "cost_history": []
  }
}
```

Design rules:

1. **`schema_version` field is mandatory.** Every load path checks this first. The `schema_version` value references a specific JSON Schema file (e.g., version 1 maps to `schemas/game_save_v1.json`). Migration functions map version N to N+1 in a chain. No skip-version migrations.
2. **JSON Schema validation on save and load.** The save format is validated against `schemas/game_save.json` (a meta-schema that resolves the correct versioned schema) on every save and load operation, following the pattern established in `agrogame/config/schemas/crop_preset.json`. Save operations that fail validation raise `SaveValidationError` and do not write to disk. Load operations that fail validation raise `LoadValidationError` with a diagnostic message identifying the failing fields.
3. **`SoilSnapshot.to_dict()` is reused as-is** for the soil portion of each field. No parallel serialization path.
4. **Root zone state is included.** Root depth accumulates over the growing season based on daily growth increments that depend on soil water content, layer impedance, and temperature -- not just GDD. Because this accumulation cannot be faithfully recalculated from GDD alone, `root_state` is persisted per field. This includes `current_depth_cm`, `distribution` type, and per-layer root fractions.
5. **Weather state is excluded.** Weather is generated from climate preset + RNG seed + day counter. Store the seed, not the timeseries.
6. **JSON for now, MessagePack later.** JSON is human-readable and diff-friendly in Git. If save files exceed 10 MB (unlikely below 200 fields), swap the serialization layer to MessagePack with the same dict structure. The `schema_version` field makes this migration mechanical.
7. **Atomic writes.** Write to a `.tmp` file, then `os.replace()` to the target path. No half-written saves on crash.
8. **One save file per game slot.** No database, no SQLite. File-based saves are portable and inspectable.

Load pseudocode:

```python
raw = json.loads(path.read_text())
validate_save_schema(raw)  # raises LoadValidationError on failure
version = raw["schema_version"]
while version < CURRENT_VERSION:
    raw = MIGRATIONS[version](raw)
    version += 1
    validate_save_schema(raw)  # re-validate after each migration step
game_state = GameState.from_dict(raw)
```

## Consequences

**Positive:**
- Developers can inspect and hand-edit saves during development and debugging.
- `SoilSnapshot` serialization is already tested; reusing it avoids a second code path.
- Schema versioning prevents breaking existing saves when new fields are added.
- Atomic writes prevent save corruption on unexpected shutdown.
- JSON Schema validation on both save and load catches structural regressions early. Schema validation runs in CI against fixture save files, forming a pipeline that guarantees every migration produces a valid save.
- Persisting root state ensures accurate mid-season save/load without lossy recalculation.

**Negative:**
- JSON is verbose. A 50-field save with full soil layer data and root state will be 2-5 MB. Acceptable for V1.
- Migration chain must be maintained indefinitely. Every schema change needs a migration function, a corresponding schema file, and a test with a fixture save file from the prior version.
- No partial load -- the entire file is deserialized into memory. Fine for <10 MB; revisit if we add detailed daily history logging.
- Schema validation adds a small overhead per save/load (~5-10 ms for a 5 MB file). Negligible compared to simulation step time.

## Alternatives Considered

**SQLite per save slot.** Enables partial reads and querying, but adds complexity for a game that loads everything into memory anyway. SQLite also makes diffs and manual inspection harder. Rejected for V1.

**YAML.** More human-readable than JSON for nested structures, but slower to parse (~3-5x), and PyYAML has known gotchas with implicit type coercion (e.g., `NO` becomes `False`). We already hit YAML key issues in AGRO-32. Rejected.

**Pickle/shelve.** Fast but not human-readable, not portable across Python versions, and a security risk if saves are ever shared. Rejected permanently.

**Separate file per field.** Avoids loading all fields at once, but adds save-directory management, risks partial saves (field 3 of 50 written before crash), and complicates atomic save. Rejected.

**MessagePack from the start.** Premature optimization. JSON parse time for a 5 MB file is ~30 ms on modern hardware. Switch when we have evidence of a problem, not before.

**Excluding root state (original design).** The original plan treated root distribution as ephemeral, recalculated from crop parameters and accumulated GDD on load. However, root depth growth depends on daily soil water content and layer impedance, making GDD-only reconstruction lossy. Including root state adds ~200 bytes per field and eliminates a class of mid-season save/load bugs.
