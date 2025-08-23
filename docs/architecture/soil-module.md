# Soil Module

The soil module defines soil profiles and layers and integrates with the soil water model abstraction.

- Profiles are defined in `soils/presets.yaml` and loaded via `agrogame.soil.loader`.
- Water balance is implemented through a pluggable interface; see [Water Model Abstraction](water_model_abstraction.md).

Key responsibilities:
- Validate layer hydraulic properties (FC/LL/SAT bounds)
- Provide layer depths and properties to the water model
- Serve as the source of truth for soil state in the orchestrator
