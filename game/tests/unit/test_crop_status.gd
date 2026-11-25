extends GutTest
## CropStatus (#630): the stage, root and damage text and the damage tally.

const HEAT := "HeatDamageApplied"
const FROST := "FrostDamageApplied"


func _tile(field: String = "f", patch: int = 0) -> Dictionary:
	var tile := {"field_id": field, "patch_idx": patch, "crop_key": "maize"}
	CropStatus.reset_tally(tile)
	return tile


## One snapshot per day for (field, patch); `events` maps a 1-based day to its events.
func _days(n: int, events: Dictionary, first: int = 1, dvs0: float = 0.5) -> Array:
	var out: Array = []
	for d in range(first, first + n):
		(
			out
			. append(
				{
					"field_id": "f",
					"patch_idx": 0,
					"crop_stage": "vegetative",
					"dev_stage": dvs0 + 0.01 * d,
					"events": events.get(d, []),
				}
			)
		)
	return out


func _heat(threshold: Variant = 35.0) -> Array:
	var data := {"tmax_c": 36.0}
	if threshold != null:
		data["threshold_c"] = threshold
	return [{"event_type": HEAT, "data": data}]


func _frost(loss: float, threshold: Variant = 0.0) -> Array:
	var data := {"lai_loss": loss, "severity": 0.5}
	if threshold != null:
		data["threshold_c"] = threshold
	return [{"event_type": FROST, "data": data}]


func _lines(tile: Dictionary) -> Array:
	return CropStatus.damage_lines(tile).map(func(l: Dictionary) -> String: return l["text"])


func test_stage_text_exact_strings() -> void:
	assert_eq(CropStatus.stage_text("grain_fill", 1.621, "maize"), "Grain fill · DVS 1.62")
	assert_eq(CropStatus.stage_text("maturity", 2.0, "maize"), "Mature — ready to harvest")
	assert_eq(CropStatus.stage_text("grain_fill", 1.5, "grape"), "Berry growth · DVS 1.50")
	assert_eq(CropStatus.stage_text("maturity", 2.0, "grape"), "Ripe — ready to harvest")
	assert_eq(CropStatus.stage_text("", -1.0, ""), "—")
	assert_eq(CropStatus.stage_text("planted", -1.0, "maize"), "Sown")
	assert_eq(CropStatus.stage_text("", -1.0, "maize"), "Sown", "a crop not yet stepped")
	assert_eq(CropStatus.stage_text("vegetative", -1.0, "maize"), "Vegetative", "no DVS yet")
	assert_eq(CropStatus.stage_text("dormant", 0.3, "maize"), "Dormant", "unknown: capitalised")


func test_every_stage_has_both_labels_and_a_tooltip() -> void:
	for name: String in CropStatus.STAGES:
		for crop: String in ["maize", "grape"]:
			var label := CropStatus.stage_text(name, 1.0, crop)
			assert_false(label.is_empty(), "%s %s" % [name, crop])
			assert_string_contains(CropStatus.stage_tooltip(name, crop), "BBCH")


func test_stage_tooltip_gives_the_bbch_range_and_the_dvs_scale() -> void:
	var tip := CropStatus.stage_tooltip("grain_fill", "maize")
	assert_eq(tip, "Grain fill: BBCH 71–85. DVS 0 = sowing, 1 = flowering, 2 = maturity.")
	assert_string_contains(CropStatus.stage_tooltip("maturity", "grape"), "BBCH 89")
	assert_string_contains(CropStatus.stage_tooltip("vegetative", "grape"), "BBCH 11–57")
	assert_string_contains(CropStatus.stage_tooltip("", "maize"), "BBCH 00–08", "unstepped crop")
	assert_eq(CropStatus.stage_tooltip("", ""), CropStatus.DVS_NOTE, "bare tile")


func test_root_text() -> void:
	assert_eq(CropStatus.root_text(107.6, "maize"), "Roots 108 cm")
	assert_eq(CropStatus.root_text(12.7, "maize"), "Roots 13 cm")
	assert_eq(CropStatus.root_text(0.0, "maize"), "Roots —")
	assert_eq(CropStatus.root_text(50.0, ""), "Roots —", "bare")


func test_heat_on_day_3_only_counts_one_day() -> void:
	var tile := _tile()
	CropStatus.tally_step(_days(7, {3: _heat()}), [tile])
	assert_eq(_lines(tile), ["Heat: 1 day above 35 °C during flowering or grain fill"])


func test_heat_on_day_7_only_counts_one_day() -> void:
	# Day 7 is also in patches[...].events; the tally reads the snapshots only.
	var tile := _tile()
	CropStatus.tally_step(_days(7, {7: _heat(32.5)}), [tile])
	assert_eq(_lines(tile), ["Heat: 1 day above 32.5 °C during flowering or grain fill"])


func test_damage_accumulates_across_steps_and_keeps_through_a_calm_one() -> void:
	var tile := _tile()
	CropStatus.tally_step(_days(7, {1: _heat(), 3: _heat(), 5: _heat()}), [tile])
	CropStatus.tally_step(_days(7, {9: _heat(), 11: _heat()}, 8), [tile])
	assert_eq(_lines(tile), ["Heat: 5 days above 35 °C during flowering or grain fill"])
	CropStatus.tally_step(_days(7, {}, 15), [tile])
	assert_eq(_lines(tile), ["Heat: 5 days above 35 °C during flowering or grain fill"])


func test_grape_heat_reads_fruit_growth() -> void:
	var tile := _tile()
	tile["crop_key"] = "grape"
	CropStatus.tally_step(_days(3, {1: _heat(38.0), 2: _heat(38.0), 3: _heat(38.0)}), [tile])
	assert_eq(_lines(tile), ["Heat: 3 days above 38 °C during flowering or berry growth"])


func test_frost_sums_lai_loss_and_both_rows_can_show() -> void:
	var tile := _tile()
	CropStatus.tally_step(_days(7, {2: _frost(0.25), 6: _frost(0.15)}), [tile])
	assert_eq(_lines(tile), ["Frost: 2 days below 0 °C, LAI −0.40"])
	CropStatus.tally_step(_days(1, {8: _heat()}, 8), [tile])
	assert_eq(_lines(tile).size(), 2, "heat and frost rows together")
	assert_eq(CropStatus.damage_lines(tile)[0]["kind"], "heat")
	assert_eq(CropStatus.damage_lines(tile)[1]["kind"], "frost")


func test_a_dvs_fall_resets_the_tally_and_counts_the_new_crop() -> void:
	# Two seasons: the rollover replants silently, DVS 2.00 -> 0.01.
	var tile := _tile()
	var season_one := _days(3, {1: _heat(), 2: _heat()}, 1, 1.9)
	CropStatus.tally_step(season_one, [tile])
	assert_eq(tile["heat_days"], 2)
	var season_two := _days(2, {2: _heat(32.0)})
	season_two[0]["dev_stage"] = 0.01
	season_two[1]["dev_stage"] = 0.02
	CropStatus.tally_step(season_two, [tile])
	assert_eq(tile["heat_days"], 1, "season one's two days are gone, season two's counted")
	assert_eq(tile["heat_threshold"], 32.0, "the latest event's threshold")


func test_a_snapshot_without_a_crop_resets_the_tally() -> void:
	var tile := _tile()
	CropStatus.tally_step(_days(3, {1: _heat()}), [tile])
	var bare := _days(1, {}, 4)
	bare[0]["crop_stage"] = ""
	CropStatus.tally_step(bare, [tile])
	assert_eq(CropStatus.damage_lines(tile), [])
	assert_eq(tile["tally_dvs"], -1.0)


func test_each_patch_and_field_has_its_own_tally() -> void:
	var a := _tile("f", 0)
	var b := _tile("f", 1)
	var c := _tile("g", 0)
	CropStatus.tally_step(_days(2, {1: _heat()}), [a, b, c])
	assert_eq(a["heat_days"], 1)
	assert_eq(b["heat_days"], 0)
	assert_eq(c["heat_days"], 0)


func test_tiles_sharing_a_patch_share_its_tally() -> void:
	var a := _tile()
	var b := _tile()
	CropStatus.tally_step(_days(2, {1: _heat()}), [a, b])
	assert_eq([a["heat_days"], b["heat_days"]], [1, 1])


func test_frost_and_cold_wording_follows_the_threshold() -> void:
	var wheat := _tile()
	CropStatus.tally_step(_days(1, {1: _frost(0.1, -2.0)}), [wheat])
	assert_eq(_lines(wheat), ["Frost: 1 day below −2 °C, LAI −0.10"])
	var rice := _tile()
	var events: Dictionary = {}
	for d in range(1, 8):
		events[d] = _frost(0.08, 10.0)
	CropStatus.tally_step(_days(7, events), [rice])
	assert_eq(_lines(rice), ["Cold: 7 days below 10 °C, LAI −0.56"])
	var sorghum := _tile()
	CropStatus.tally_step(_days(1, {1: _frost(0.2, 2.0)}), [sorghum])
	assert_eq(_lines(sorghum), ["Cold: 1 day below 2 °C, LAI −0.20"])


func test_a_missing_threshold_drops_the_clause_and_invents_none() -> void:
	var tile := _tile()
	CropStatus.tally_step(_days(2, {1: _heat(null), 2: _heat(null)}), [tile])
	assert_eq(_lines(tile), ["Heat: 2 days during flowering or grain fill"])
	var cold := _tile()
	CropStatus.tally_step(_days(1, {1: _frost(0.3, null)}), [cold])
	assert_eq(_lines(cold), ["Frost: 1 day, LAI −0.30"])


func test_maize_24_heat_days_read_as_refined() -> void:
	var tile := _tile()
	var events: Dictionary = {}
	for d in range(1, 25):
		events[d] = _heat()
	CropStatus.tally_step(_days(24, events), [tile])
	assert_eq(_lines(tile), ["Heat: 24 days above 35 °C during flowering or grain fill"])
