Phenology summary

- GDD accumulation with base/max temperature caps
- Optional photoperiod multiplier; optional vernalization units gate
- Stages: PLANTED → EMERGED → VEGETATIVE → FLOWERING → GRAIN_FILL → MATURITY
- Events: `GddAccumulated`, `StageChanged`

Factory: `build_from_crop_params` maps `CropParameters.thermal_time` to phenology params.


