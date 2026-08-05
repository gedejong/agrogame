extends GutTest
## Unit tests for ScenarioCatalog — the curated start-of-game scenarios (#440).

const ScenarioCatalogScript = preload("res://scripts/scenario_catalog.gd")

# Preset keys that exist in data/*/presets.yaml — scenarios must only use these.
const VALID_CROPS := [
	"maize", "winter_wheat", "spring_wheat", "rice", "sorghum", "soybean", "grape"
]
const VALID_CLIMATES := ["netherlands_temperate", "kenya_highlands", "sahel_arid"]
const VALID_SOILS := [
	"sandy_arid",
	"sandy_temperate",
	"loam_temperate",
	"clay_temperate",
	"clay_netherlands",
	"sandy_loam_temperate",
	"clay_loam_temperate",
	"peat_cool_wet",
	"sandy_subsaharan",
]


func test_offers_multiple_scenarios() -> void:
	assert_gt(ScenarioCatalogScript.option_count(), 1, "Catalog should offer several scenarios")


func test_default_id_is_valid() -> void:
	assert_true(
		ScenarioCatalogScript.is_valid(ScenarioCatalogScript.DEFAULT_ID),
		"DEFAULT_ID must address a real scenario",
	)


func test_is_valid_rejects_out_of_range() -> void:
	assert_false(ScenarioCatalogScript.is_valid(-1), "Negative id is invalid")
	assert_false(
		ScenarioCatalogScript.is_valid(ScenarioCatalogScript.option_count()),
		"Id at option_count is out of range",
	)


func test_labels_present_for_all_options() -> void:
	for i in range(ScenarioCatalogScript.option_count()):
		assert_ne(ScenarioCatalogScript.label_for(i), "", "Scenario %d should have a label" % i)


func test_label_out_of_range_is_empty() -> void:
	assert_eq(ScenarioCatalogScript.label_for(-1), "", "Out-of-range label should be empty")


func test_all_scenario_keys_are_real_presets() -> void:
	for i in range(ScenarioCatalogScript.option_count()):
		for patch in ScenarioCatalogScript.patches_for(i):
			assert_has(VALID_CROPS, patch["crop_key"], "crop_key must be a real preset")
			assert_has(VALID_CLIMATES, patch["climate_key"], "climate_key must be a real preset")
			assert_has(VALID_SOILS, patch["soil_profile_key"], "soil key must be a real preset")


func test_area_fractions_sum_to_one() -> void:
	for i in range(ScenarioCatalogScript.option_count()):
		var total: float = 0.0
		for patch in ScenarioCatalogScript.patches_for(i):
			total += patch["area_fraction"]
		assert_almost_eq(total, 1.0, 0.001, "Scenario %d area fractions should sum to 1" % i)


func test_default_scenario_preserves_three_patch_nl_maize() -> void:
	# Quick-start default must reproduce the historical 3-patch NL-maize layout.
	var patches: Array = ScenarioCatalogScript.default_patches()
	assert_eq(patches.size(), 3, "Default scenario should have three patches")
	for patch in patches:
		assert_eq(patch["crop_key"], "maize", "Default is NL maize")
		assert_eq(patch["climate_key"], "netherlands_temperate", "Default is NL maize")


func test_patches_out_of_range_is_empty() -> void:
	assert_eq(ScenarioCatalogScript.patches_for(-1), [], "Out-of-range patches should be empty")


func test_patches_for_returns_a_copy() -> void:
	# Mutating a returned patch list must not corrupt the shared catalog.
	var first: Array = ScenarioCatalogScript.patches_for(ScenarioCatalogScript.DEFAULT_ID)
	first[0]["crop_key"] = "mutated"
	var second: Array = ScenarioCatalogScript.patches_for(ScenarioCatalogScript.DEFAULT_ID)
	assert_eq(second[0]["crop_key"], "maize", "Catalog data should be immutable to callers")


func test_selects_a_non_default_scenario() -> void:
	# There is at least one non-default scenario mapping to a distinct crop or climate.
	var found_non_default := false
	for i in range(ScenarioCatalogScript.option_count()):
		if i == ScenarioCatalogScript.DEFAULT_ID:
			continue
		if (
			ScenarioCatalogScript.crop_for(i) != "maize"
			or ScenarioCatalogScript.climate_for(i) != "netherlands_temperate"
		):
			found_non_default = true
	assert_true(found_non_default, "Catalog should include non-default scenarios")


func test_accessors_out_of_range_are_empty() -> void:
	assert_eq(ScenarioCatalogScript.crop_for(-1), "", "crop_for out of range is empty")
	assert_eq(ScenarioCatalogScript.climate_for(-1), "", "climate_for out of range is empty")
	assert_eq(ScenarioCatalogScript.soil_for(-1), "", "soil_for out of range is empty")


func test_accessors_match_first_patch() -> void:
	var kenya_rice_idx := -1
	for i in range(ScenarioCatalogScript.option_count()):
		if ScenarioCatalogScript.crop_for(i) == "rice":
			kenya_rice_idx = i
	assert_gt(kenya_rice_idx, -1, "Catalog should include a rice scenario")
	assert_eq(ScenarioCatalogScript.climate_for(kenya_rice_idx), "kenya_highlands")
	assert_eq(ScenarioCatalogScript.soil_for(kenya_rice_idx), "clay_temperate")
