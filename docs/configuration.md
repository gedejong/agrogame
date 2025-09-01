### Configuration schemas and tools

AgroGame provides versioned JSON Schemas and a small CLI to validate and compose configuration files.

- Schemas live under `agrogame/config/schemas/` and cover: crop, soil, weather (JSON), and management events.
- Validate with:
```bash
poetry run agrogame validate crop samples/crops.yaml
poetry run agrogame validate soil soils/presets.yaml
```
- Compose multiple layers and build a final YAML:
```bash
poetry run agrogame build crop out.yaml base.yaml override.yaml
```
- Watch files and emit a `ConfigReloaded` event on changes (for UIs/integration):
```bash
poetry run agrogame watch crop samples/crops.yaml
```

Units and ranges are documented inline in the schema and mirrored in the Pydantic models under `agrogame/params/models.py` and `agrogame/soil/models.py`.


