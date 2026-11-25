extends GutTest
## FarmTiles: the tile-grid builder and per-patch tile writer moved out of
## farm_view.gd unchanged (#546).

const FarmView = preload("res://scripts/farm_view.gd")


func _nutrient(nutrient: String, data: Dictionary) -> Dictionary:
	data["nutrient"] = nutrient
	return {"event_type": "NutrientStressComputed", "data": data}


## Stress values in thousandths, so float rounding cannot flake a comparison.
func _stress(events: Array, keys: Array) -> Array:
	var s := FarmTiles.stress_from_events(events)
	return keys.map(func(k: String) -> int: return roundi(float(s[k]) * 1000.0))


func test_nutrient_stress_is_max_of_inverted_clamped_value() -> void:
	# API stress: 1 healthy, 0 severe; distinct values catch a cross-wired nutrient.
	var events: Array = [
		_nutrient("N", {"stress": 0.6}),
		_nutrient("N", {"stress": 0.2}),  # 0.8, the max
		_nutrient("N", {"stress": 1.5}),  # clamps to 0
		_nutrient("P", {"stress": -0.3}),  # clamps to 1
		_nutrient("Fe", {"stress": 0.75}),
		_nutrient("Zn", {}),  # missing stress is healthy
		_nutrient("Zn", {"stress": 0.9}),
		_nutrient("Mn", {"stress": 0.0}),  # read since #660, see the next test
		{"event_type": "WaterStressComputed", "data": {"nutrient": "N", "stress": 0.0}},
	]
	var keys := ["n_stress", "p_stress", "fe_stress", "zn_stress", "frost_damage"]
	assert_eq(_stress(events, keys), [800, 1000, 250, 100, 0])
	assert_eq(_stress([], keys), [0, 0, 0, 0, 0], "no events, no stress")


func test_sulfur_manganese_and_todays_ks_are_read() -> void:
	# #660: the Nutrients gauge takes all six nutrients; Water reads the last Ks.
	var events: Array = [
		_nutrient("S", {"stress": 0.49}),
		_nutrient("Mn", {"stress": 0.8}),
		{"event_type": "WaterStressComputed", "data": {"stress": 0.2}},
		{"event_type": "WaterStressComputed", "data": {"stress": 0.7}},  # the last wins
	]
	var keys := ["s_stress", "mn_stress", "water_ks"]
	assert_eq(_stress(events, keys), [510, 200, 700])
	assert_eq(_stress([], keys), [0, 0, 1000], "no events: no stress, Ks 1")


func test_write_patch_stores_the_gauge_fields_and_null_as_minus_one() -> void:
	var tiles: Array = [{"field_id": "f", "patch_idx": 0, "crop_key": ""}]
	var ks0 := {"event_type": "WaterStressComputed", "data": {"stress": 0.0}}
	var patch := {"crop_key": "rice", "crop_stage": "grain_fill", "events": [ks0]}
	patch.merge({"growth_vs_potential": 0.499, "root_zone_water_fraction": 1.3})
	patch["depletion_fraction_p"] = 0.2
	FarmTiles.write_patch(patch, "f", 0, tiles)
	var keys := ["growth_vs_potential", "root_zone_water_fraction", "depletion_fraction_p"]
	keys.append("water_ks")
	assert_eq(keys.map(func(k: String) -> float: return tiles[0][k]), [0.499, 1.3, 0.2, 0.0])
	var bare := {"crop_key": "", "growth_vs_potential": null, "depletion_fraction_p": null}
	FarmTiles.write_patch(bare, "f", 0, tiles)
	assert_eq(keys.map(func(k: String) -> float: return tiles[0][k]), [-1.0, -1.0, -1.0, 1.0])


func test_frost_and_heat_severity_default_half_clamp_and_max() -> void:
	var keys := ["frost_damage", "heat_damage", "n_stress"]
	var frost := "FrostDamageApplied"
	var heat := "HeatDamageApplied"
	# Frost reads its severity; heat is presence-only (#664): the constant, and
	# the event's fields do not move it.
	var defaults: Array = [{"event_type": frost}, {"event_type": heat, "data": {"x": 1}}]
	assert_eq(_stress(defaults, keys), [500, 500, 0], "default 0.5")
	# Above 1 clamps to 1. Below 0 reads as 0 either way: the max starts at 0.
	var high: Array = [
		{"event_type": frost, "data": {"severity": 3.0}},
	]
	assert_eq(_stress(high, keys), [1000, 0, 0], "frost clamped to [0, 1]")
	var many: Array = [
		{"event_type": frost, "data": {"severity": 0.2}},
		{"event_type": frost, "data": {"severity": 0.7}},
		{"event_type": heat, "data": {"tmax_c": 39.0, "threshold_c": 35.0}},
		{"event_type": heat},
	]
	assert_eq(_stress(many, keys), [700, 500, 0], "max over events")


## A HeatDamageApplied as /step sends it: tmax_c and threshold_c, no severity.
func _heat(tmax_c: float, threshold_c: float) -> Dictionary:
	return {
		"event_type": "HeatDamageApplied",
		"module": "agrogame.soil.canopy.events",
		"data": {"tmax_c": tmax_c, "threshold_c": threshold_c},
	}


func test_heat_severity_is_presence_only() -> void:
	# #664: the event carries exposure (tmax_c, threshold_c), no grain factor, and
	# the tint is the same constant whatever it carries.
	var keys := ["heat_damage"]
	var constant := int(FarmTiles.HEAT_PRESENCE_SEVERITY * 1000)
	assert_eq(FarmTiles.heat_severity(), FarmTiles.HEAT_PRESENCE_SEVERITY, "the UI constant")
	assert_eq(_stress([_heat(36.0, 35.0)], keys), [constant], "maize day")
	assert_eq(_stress([_heat(44.0, 32.0)], keys), [constant], "a much hotter day, same tint")
	var bare: Dictionary = {"event_type": "HeatDamageApplied", "data": {"tmax_c": 34.0}}
	assert_eq(_stress([bare], keys), [constant], "threshold_c is not needed to set it")
	var stale := _heat(34.0, 32.0)
	stale["data"]["grain_reduction_factor"] = 0.1
	assert_eq(_stress([stale], keys), [constant], "a grain factor is ignored")


func test_debug_heat_event_writes_the_tile_the_engine_event_does() -> void:
	# The debug injector emits the engine's field shape, so the debug path and
	# the real /step path leave a tile in the same state for the same event.
	var heat := "HeatDamageApplied"
	var patches := {"field_1": [{"events": []}]}
	FarmViewDebug.inject_debug_stress_events(patches)
	var debug_events: Array = patches["field_1"][0]["events"]
	var debug_heat: Array = debug_events.filter(
		func(e: Dictionary) -> bool: return e["event_type"] == heat
	)
	assert_eq(debug_heat.size(), 1, "one debug heat event")
	var fields: Array = (debug_heat[0]["data"] as Dictionary).keys()
	fields.sort()
	assert_eq(fields, ["threshold_c", "tmax_c"], "the engine's fields, no more")
	var real_events: Array = debug_events.map(
		func(e: Dictionary) -> Dictionary:
			return _heat(34.0, 32.0) if e["event_type"] == heat else e
	)
	var tiles: Array = [
		[{"field_id": "field_1", "patch_idx": 0}], [{"field_id": "field_1", "patch_idx": 0}]
	]
	FarmTiles.write_patch({"events": debug_events}, "field_1", 0, tiles[0])
	FarmTiles.write_patch({"events": real_events}, "field_1", 0, tiles[1])
	assert_eq(tiles[0][0], tiles[1][0], "same tile state")
	assert_eq(tiles[0][0]["heat_damage"], FarmTiles.HEAT_PRESENCE_SEVERITY, "the presence tint")


func test_writes_reach_only_tiles_with_matching_patch_idx() -> void:
	var tiles: Array = []
	for idx: int in [0, 0, 1, 1, 2, 2]:
		tiles.append({"field_id": "field_1", "patch_idx": idx, "crop_key": "", "lai": 0.0})
	var before: Array = tiles.duplicate(true)
	var patch := {
		"crop_key": "rice",
		"crop_stage": "grain_fill",
		"lai": 2.0,
		"events": [_nutrient("N", {"stress": 0.25})],
	}
	assert_eq(FarmTiles.write_patch(patch, "field_1", 1, tiles), [2, 3] as Array[int], "ascending")
	for i: int in [0, 1, 4, 5]:
		assert_eq(tiles[i], before[i], "tile %d untouched" % i)
	for i: int in [2, 3]:
		var t: Dictionary = tiles[i]
		assert_eq([t["crop_key"], t["crop_stage"], t["lai"], t["n_stress"]], ["rice", 4, 2.0, 0.75])
	assert_eq(
		FarmTiles.write_patch(patch, "field_1", 7, tiles), [] as Array[int], "no tiles, no writes"
	)


func test_lai_peak_held_only_past_emergence_with_the_same_crop() -> void:
	var tiles: Array = [{"field_id": "field_1", "patch_idx": 0}]
	var steps: Array = [  # crop, stage, lai, expected lai_peak
		["maize", "vegetative", 2.0, 2.0],
		["maize", "vegetative", 3.5, 3.5],
		["maize", "grain_fill", 2.5, 3.5],  # canopy loss: peak holds
		["rice", "vegetative", 1.0, 1.0],  # crop changed: reset
		["rice", "emerged", 0.3, 0.3],  # stage 1: reset, same crop
		["rice", "vegetative", 0.2, 0.3],
		["rice", "unknown", 0.1, 0.1],  # stage 0: reset
	]
	for step: Array in steps:
		var patch := {"crop_key": step[0], "crop_stage": step[1], "lai": step[2]}
		FarmTiles.write_patch(patch, "field_1", 0, tiles)
		assert_eq(tiles[0]["lai_peak"], step[3], "%s %s" % [step[0], step[1]])


func test_lai_peak_does_not_carry_into_the_next_season() -> void:
	# Sowing maize again (stage 1) drops season one's 4.5 peak.
	var tiles: Array = [{"field_id": "field_1", "patch_idx": 0}]
	for peak: float in [4.5, 2.0]:
		for day: Array in [
			["planted", 0.0, 0.0], ["vegetative", peak, peak], ["maturity", 1.0, peak]
		]:
			var patch := {"crop_key": "maize", "crop_stage": day[0], "lai": day[1]}
			FarmTiles.write_patch(patch, "field_1", 0, tiles)
			assert_eq(tiles[0]["lai_peak"], day[2], "season peak %.1f, %s" % [peak, day[0]])


func test_builder_yields_36_tiles_at_todays_positions() -> void:
	var roots: Array[Node3D] = [Node3D.new(), Node3D.new()]
	for root: Node3D in roots:
		add_child_autofree(root)
	var grid := Vector2i(FarmView.GRID_COLS, FarmView.GRID_ROWS)
	var built := FarmTiles.build_grid(roots[0], roots[1], grid, FarmView.TILE_SIZE)
	for key: String in ["meshes", "materials", "crop_sprites", "tile_data"]:
		assert_eq((built[key] as Array).size(), 36, key)
	assert_eq([roots[0].get_child_count(), roots[1].get_child_count()], [36, 36], "parented")
	assert_eq((built["meshes"][35] as MeshInstance3D).position, Vector3(2.5, 0.0, 2.5))
	assert_ne(built["materials"][0], built["materials"][1], "per-tile selection highlight")
	for i in range(36):
		var col: int = i % 6
		var row: int = floori(i / 6.0)
		var mesh: MeshInstance3D = built["meshes"][i]
		assert_eq(mesh.position, Vector3(col - 2.5, 0.0, row - 2.5), "1 m tiles, centred")
		assert_same(mesh.material_override, built["materials"][i])
		var body: StaticBody3D = mesh.get_child(0)
		assert_eq([body.get_meta("tile_col"), body.get_meta("tile_row")], [col, row])
		assert_eq((built["crop_sprites"][i][0] as Node3D).position, mesh.position, "crops")
		var data: Dictionary = built["tile_data"][i]
		assert_eq(
			[data["col"], data["row"], data["crop_key"], data["crop_stage"]], [col, row, "", 0]
		)


## Six tiles, one per column, of a 1.2-DVS maize crop, laid out as the default
## scenario's field_1: columns 0-1 are patch 0, 2-3 patch 1 and 4-5 patch 2.
func _laid_out_maize() -> Array:
	var tiles: Array = []
	var mats: Array = []
	for col in range(6):
		var tile := {"col": col, "crop_key": "maize", "crop_stage": 3, "lai": 2.5}
		tile.merge({"lai_peak": 3.0, "dev_stage": 1.2, "grain_g_m2": 40.0})
		tiles.append(tile)
		mats.append(ShaderMaterial.new())
	FarmLayout.assign_fields(ScenarioCatalog.default_fields(), tiles, mats, Vector2i(6, 6))
	return tiles


func _column(tiles: Array, key: String) -> Array:
	return tiles.map(func(t: Dictionary) -> Variant: return t[key])


func test_reconcile_crops_matches_tiles_by_field_and_patch() -> void:
	# #564: after a failed action, GET /games/{id}'s crops are the truth. A tile
	# is matched by its field_id and patch_idx, so field_2's patch 0 never lands
	# on field_1's patch 0, and only the tiles whose crop differs are rewritten.
	var tiles := _laid_out_maize()
	assert_eq(
		_column(tiles, "field_id"),
		["field_1", "field_1", "field_1", "field_1", "field_1", "field_1"]
	)
	var fields := {
		"field_2": [{"crop_key": "rice"}],
		"field_1": [{"crop_key": "maize"}, {"crop_key": ""}, {"crop_key": "sorghum"}],
	}
	assert_eq(FarmTiles.reconcile_crops(fields, tiles), [2, 3, 4, 5], "patches 1 and 2 changed")
	assert_eq(_column(tiles, "crop_key"), ["maize", "maize", "", "", "sorghum", "sorghum"])
	# Patch 0 keeps its growth; patch 1 is bare and patch 2 freshly sown, as a
	# Harvest and a Plant reply leave them, with nothing of the old crop's left.
	assert_eq(_column(tiles, "crop_stage"), [3, 3, 0, 0, 1, 1])
	assert_eq(_column(tiles, "lai"), [2.5, 2.5, 0.0, 0.0, 0.0, 0.0])
	assert_eq(_column(tiles, "lai_peak"), [3.0, 3.0, 0.0, 0.0, 0.0, 0.0])
	assert_eq(_column(tiles, "dev_stage"), [1.2, 1.2, -1.0, -1.0, -1.0, -1.0])
	assert_eq(_column(tiles, "grain_g_m2"), [40.0, 40.0, 0.0, 0.0, 0.0, 0.0])
	# A second pass over the same truth changes nothing.
	assert_eq(FarmTiles.reconcile_crops(fields, tiles), [], "idempotent")
	# Tiles of a field the payload lacks, or of a patch past its list, are kept.
	assert_eq(FarmTiles.reconcile_crops({"field_2": [{"crop_key": ""}]}, tiles), [])
	assert_eq(FarmTiles.reconcile_crops({"field_1": [{"crop_key": "rice"}]}, tiles), [0, 1])
	assert_eq(_column(tiles, "crop_key"), ["rice", "rice", "", "", "sorghum", "sorghum"])


func _snap(day: int, events: Array, field: String = "f", patch: int = 0) -> Dictionary:
	return {"day_number": day, "field_id": field, "patch_idx": patch, "events": events}


func test_latch_step_damage_appends_earlier_days_damage_only() -> void:
	# A 7-day step: heat on day 3 only. The patch holds day 7's events (none).
	var heat := {"event_type": "HeatDamageApplied", "data": {"tmax_c": 36.0, "threshold_c": 35.0}}
	var other := {"event_type": "WaterStressComputed", "data": {"stress": 0.1}}
	var snaps: Array = []
	for d in range(1, 8):
		snaps.append(_snap(d, [heat, other] if d == 3 else []))
	snaps.append(_snap(7, [heat], "f", 9))  # a patch the payload lacks: skipped
	snaps.append(_snap(7, [heat], "x", 0))  # a field it lacks: skipped
	var patches := {"f": [{"events": []}]}
	FarmTiles.latch_step_damage(snaps, patches)
	assert_eq(patches["f"][0]["events"], [heat], "damage only, not the drought event")
	var latched: Dictionary = FarmTiles.stress_from_events(patches["f"][0]["events"])
	assert_eq(latched["heat_damage"], FarmTiles.HEAT_PRESENCE_SEVERITY)
	var bare := {"f": [{}]}
	FarmTiles.latch_step_damage([_snap(1, [heat])], bare)
	assert_eq(bare["f"][0]["events"], [heat], "a patch without an events list gets one")


func test_write_patch_stores_stage_name_and_roots() -> void:
	var tiles: Array = [{"field_id": "f", "patch_idx": 0, "crop_key": ""}]
	var patch := {"crop_key": "maize", "crop_stage": "grain_fill", "root_depth_cm": 107.6}
	FarmTiles.write_patch(patch, "f", 0, tiles)
	assert_eq(tiles[0]["crop_stage_name"], "grain_fill")
	assert_eq(tiles[0]["root_depth_cm"], 107.6)


func test_clear_and_sow_reset_the_crop_and_only_that_patch() -> void:
	var tiles: Array = []
	for pi in [0, 1]:
		var t := {"field_id": "f", "patch_idx": pi, "crop_key": "maize"}
		(
			t
			. merge(
				{
					"crop_stage_name": "grain_fill",
					"root_depth_cm": 80.0,
					"heat_damage": 0.5,
					"frost_damage": 0.4,
					"n_stress": 0.3,
					"heat_days": 4,
					"dev_stage": 1.5,
					"s_stress": 0.5,
					"mn_stress": 0.2,
					"water_ks": 0.1,
					"growth_vs_potential": 0.4,
					"depletion_fraction_p": 0.55,
					"root_zone_water_fraction": 0.3,
				}
			)
		)
		tiles.append(t)
	assert_eq(FarmTiles.clear_crop("f", 0, tiles), [0])
	var t0: Dictionary = tiles[0]
	assert_eq([t0["crop_key"], t0["crop_stage"], t0["crop_stage_name"]], ["", 0, ""])
	assert_eq([t0["root_depth_cm"], t0["heat_damage"], t0["frost_damage"]], [0.0, 0.0, 0.0])
	assert_eq([t0["n_stress"], t0["heat_days"], t0["dev_stage"]], [0.0, 0, -1.0])
	# #660: the gauges start afresh; root-zone water is the soil's and stays.
	assert_eq([t0["s_stress"], t0["mn_stress"], t0["water_ks"]], [0.0, 0.0, 1.0])
	assert_eq([t0["growth_vs_potential"], t0["depletion_fraction_p"]], [-1.0, -1.0])
	assert_eq(t0["root_zone_water_fraction"], 0.3)
	assert_eq(tiles[1]["heat_days"], 4, "the other patch is untouched")
	assert_eq(FarmTiles.sow_crop("rice", "f", 1, tiles), [1])
	assert_eq([tiles[1]["crop_key"], tiles[1]["crop_stage"]], ["rice", 1])
	assert_eq(tiles[1]["heat_days"], 0)


func test_reconcile_resets_stage_roots_and_damage_of_a_changed_crop() -> void:
	var tile := {"field_id": "f", "patch_idx": 0, "crop_key": "maize", "heat_days": 3}
	tile.merge({"root_depth_cm": 50.0, "heat_damage": 0.5, "crop_stage_name": "vegetative"})
	var fields := {"f": [{"crop_key": "sorghum"}]}
	assert_eq(FarmTiles.reconcile_crops(fields, [tile]), [0])
	assert_eq([tile["heat_days"], tile["root_depth_cm"], tile["heat_damage"]], [0, 0.0, 0.0])
	assert_eq(tile["crop_stage_name"], "")
