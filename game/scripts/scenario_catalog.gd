class_name ScenarioCatalog
extends RefCounted
## Curated start-of-game scenarios for the scenario picker (issue #440).
##
## Each scenario maps a human-readable name to a list of patch configs
## (crop_key, climate_key, soil_profile_key, area_fraction) that the backend's
## POST /games (CreateGameRequest) accepts directly — the keys mirror the
## presets in data/crops, data/climate and data/soils. The default scenario
## (id 0) reproduces the historical 3-patch NL-maize layout so quick-start
## behaviour is unchanged.
##
## This is a pure data/logic module (no scene, no HTTP) so it can be unit
## tested in isolation, mirroring the fertilizer_picker.gd pattern.

## Option id of the quick-start default scenario.
const DEFAULT_ID: int = 0

## Curated scenarios in display order. Every crop/climate/soil key below is a
## real preset key (data/crops/presets.yaml, data/climate/presets.yaml,
## data/soils/presets.yaml). Only netherlands_temperate, kenya_highlands and
## sahel_arid climates exist today, so the tested envelope spans those three.
const SCENARIOS: Array = [
	{
		"label": "Netherlands maize (default)",
		# Historical default: one field, three soil textures under NL maize.
		"patches":
		[
			{
				"soil_profile_key": "sandy_temperate",
				"crop_key": "maize",
				"climate_key": "netherlands_temperate",
				"area_fraction": 0.333,
			},
			{
				"soil_profile_key": "loam_temperate",
				"crop_key": "maize",
				"climate_key": "netherlands_temperate",
				"area_fraction": 0.334,
			},
			{
				"soil_profile_key": "clay_temperate",
				"crop_key": "maize",
				"climate_key": "netherlands_temperate",
				"area_fraction": 0.333,
			},
		],
	},
	{
		"label": "Kenya-highland maize",
		"patches":
		[
			{
				"soil_profile_key": "loam_temperate",
				"crop_key": "maize",
				"climate_key": "kenya_highlands",
				"area_fraction": 1.0,
			},
		],
	},
	{
		"label": "Sahel sorghum (drought)",
		"patches":
		[
			{
				"soil_profile_key": "sandy_subsaharan",
				"crop_key": "sorghum",
				"climate_key": "sahel_arid",
				"area_fraction": 1.0,
			},
		],
	},
	{
		"label": "Kenya rice",
		"patches":
		[
			{
				"soil_profile_key": "clay_temperate",
				"crop_key": "rice",
				"climate_key": "kenya_highlands",
				"area_fraction": 1.0,
			},
		],
	},
	{
		"label": "Netherlands spring wheat",
		"patches":
		[
			{
				"soil_profile_key": "clay_netherlands",
				"crop_key": "spring_wheat",
				"climate_key": "netherlands_temperate",
				"area_fraction": 1.0,
			},
		],
	},
	{
		"label": "Netherlands winter wheat",
		"patches":
		[
			{
				"soil_profile_key": "clay_netherlands",
				"crop_key": "winter_wheat",
				"climate_key": "netherlands_temperate",
				"area_fraction": 1.0,
			},
		],
	},
]


## Number of scenarios offered by the picker.
static func option_count() -> int:
	return SCENARIOS.size()


## True when option_id addresses a real scenario.
static func is_valid(option_id: int) -> bool:
	return option_id >= 0 and option_id < SCENARIOS.size()


## Display label for a scenario, or "" when out of range.
static func label_for(option_id: int) -> String:
	if not is_valid(option_id):
		return ""
	return SCENARIOS[option_id]["label"]


## Patch configs for a scenario as a fresh (deep-copied) Array of Dictionaries,
## ready to hand to ApiClient.create_game. Returns [] when out of range.
static func patches_for(option_id: int) -> Array:
	if not is_valid(option_id):
		return []
	var patches: Array = SCENARIOS[option_id]["patches"]
	return patches.duplicate(true)


## Canonical quick-start patches (the default scenario), used when no explicit
## selection is made. Always returns a valid non-empty layout.
static func default_patches() -> Array:
	return patches_for(DEFAULT_ID)


## Primary crop_key of a scenario (first patch), or "" when out of range.
## Convenience accessor for tests/HUD; scenarios are single-crop today.
static func crop_for(option_id: int) -> String:
	if not is_valid(option_id):
		return ""
	return SCENARIOS[option_id]["patches"][0]["crop_key"]


## Climate_key of a scenario (first patch), or "" when out of range.
static func climate_for(option_id: int) -> String:
	if not is_valid(option_id):
		return ""
	return SCENARIOS[option_id]["patches"][0]["climate_key"]


## Soil_profile_key of a scenario (first patch), or "" when out of range.
static func soil_for(option_id: int) -> String:
	if not is_valid(option_id):
		return ""
	return SCENARIOS[option_id]["patches"][0]["soil_profile_key"]
