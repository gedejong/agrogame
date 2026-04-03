extends RefCounted
## Base crop renderer — shared constants and fallback rendering.
## Subclass per crop for custom procedural visuals.

const _PLANT_SCALE := Vector2(0.4, 0.4)
const PLANT_GRID := 4
const PLANT_FRACS: Array[float] = [0.125, 0.375, 0.625, 0.875]
const _FALLBACK_CROP := "maize"
const _CROP_PREFIX := {
	"spring_wheat": "wheat",
	"winter_wheat": "wheat",
}

## Stage enum values matching farm_view.gd CropStage
const STAGE_SEEDLING := 1
const STAGE_VEGETATIVE := 2
const STAGE_FLOWERING := 3
const STAGE_MATURE := 4

const STRESS_WILTING := 1
const STRESS_N_DEFICIENT := 2

const STAGE_SUFFIX := {
	STAGE_SEEDLING: "seedling",
	STAGE_VEGETATIVE: "vegetative",
	STAGE_FLOWERING: "flowering",
	STAGE_MATURE: "mature",
}

const STAGE_MAP := {
	"planted": STAGE_SEEDLING,
	"emerged": STAGE_SEEDLING,
	"vegetative": STAGE_VEGETATIVE,
	"flowering": STAGE_FLOWERING,
	"grain_fill": STAGE_MATURE,
	"maturity": STAGE_MATURE,
}


static func crop_sprite_path(crop_key: String, suffix: String) -> String:
	var prefix: String = _CROP_PREFIX.get(crop_key, crop_key)
	var path := "res://assets/crops/%s_%s.svg" % [prefix, suffix]
	if ResourceLoader.exists(path):
		return path
	return "res://assets/crops/%s_%s.svg" % [_FALLBACK_CROP, suffix]


static func crop_layer_path(crop_key: String, layer_name: String) -> String:
	var prefix: String = _CROP_PREFIX.get(crop_key, crop_key)
	var path := "res://assets/crops/%s_%s.svg" % [prefix, layer_name]
	if ResourceLoader.exists(path):
		return path
	return "res://assets/crops/%s_%s.svg" % [_FALLBACK_CROP, layer_name]


static func has_layers(crop_key: String) -> bool:
	return ResourceLoader.exists(crop_layer_path(crop_key, "stem"))


static func root_hash(seed_val: int, idx: int) -> float:
	var h := (seed_val + idx * 40503) & 0x7FFFFFFF
	return float(h % 1000) / 1000.0
