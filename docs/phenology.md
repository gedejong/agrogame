---
module: agrogame.soil.phenology
doc_type: module
references:
  - "DSSAT v4.8 — GDD-based phenology with photoperiod gates"
  - "WOFOST — vernalization-modulated thermal time"
key_classes:
  - PhenologyModule
  - PhenologyState
  - PhenologyStage
  - CropPhenologyParams
  - GrowthStageThresholds
key_events:
  - GddAccumulated
  - StageChanged
primary_tests:
  - tests/test_phenology.py
related_adrs: [ADR-002]
---

Phenology summary

- GDD accumulation with base/max temperature caps
- Optional photoperiod multiplier; optional vernalization units gate
- Stages: PLANTED → EMERGED → VEGETATIVE → FLOWERING → GRAIN_FILL → MATURITY
- Events: `GddAccumulated`, `StageChanged`

Factory: `build_from_crop_params` maps `CropParameters.thermal_time` to phenology params.


