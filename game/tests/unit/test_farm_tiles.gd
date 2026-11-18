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
		_nutrient("Mn", {"stress": 0.0}),  # not displayed
		{"event_type": "WaterStressComputed", "data": {"nutrient": "N", "stress": 0.0}},
	]
	var keys := ["n_stress", "p_stress", "fe_stress", "zn_stress", "frost_damage"]
	assert_eq(_stress(events, keys), [800, 1000, 250, 100, 0])
	assert_eq(_stress([], keys), [0, 0, 0, 0, 0], "no events, no stress")


func test_frost_and_heat_severity_default_half_clamp_and_max() -> void:
	var keys := ["frost_damage", "heat_damage", "n_stress"]
	var frost := "FrostDamageApplied"
	var heat := "HeatDamageApplied"
	# The debug injector's heat event carries no severity (FAKE_STRESS_EVENTS).
	var defaults: Array = [{"event_type": frost}, {"event_type": heat, "data": {"x": 1}}]
	assert_eq(_stress(defaults, keys), [500, 500, 0], "default 0.5")
	# Above 1 clamps to 1. Below 0 reads as 0 either way: the max starts at 0.
	var high: Array = [
		{"event_type": frost, "data": {"severity": 3.0}},
		{"event_type": heat, "data": {"severity": 1.2}},
		{"event_type": heat, "data": {"severity": -2.0}},
	]
	assert_eq(_stress(high, keys), [1000, 1000, 0], "clamped to [0, 1]")
	var many: Array = [
		{"event_type": frost, "data": {"severity": 0.2}},
		{"event_type": frost, "data": {"severity": 0.7}},
		{"event_type": heat, "data": {"severity": 0.3}},
		{"event_type": heat},
	]
	assert_eq(_stress(many, keys), [700, 500, 0], "max over events")


func test_writes_reach_only_tiles_with_matching_patch_idx() -> void:
	var tiles: Array = []
	for idx: int in [0, 0, 1, 1, 2, 2]:
		tiles.append({"patch_idx": idx, "crop_key": "", "lai": 0.0})
	var before: Array = tiles.duplicate(true)
	var patch := {
		"crop_key": "rice",
		"crop_stage": "grain_fill",
		"lai": 2.0,
		"events": [_nutrient("N", {"stress": 0.25})],
	}
	assert_eq(FarmTiles.write_patch(patch, 1, tiles), [2, 3] as Array[int], "ascending")
	for i: int in [0, 1, 4, 5]:
		assert_eq(tiles[i], before[i], "tile %d untouched" % i)
	for i: int in [2, 3]:
		var t: Dictionary = tiles[i]
		assert_eq([t["crop_key"], t["crop_stage"], t["lai"], t["n_stress"]], ["rice", 4, 2.0, 0.75])
	assert_eq(FarmTiles.write_patch(patch, 7, tiles), [] as Array[int], "no tiles, no writes")


func test_lai_peak_held_only_past_emergence_with_the_same_crop() -> void:
	var tiles: Array = [{"patch_idx": 0}]
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
		FarmTiles.write_patch(patch, 0, tiles)
		assert_eq(tiles[0]["lai_peak"], step[3], "%s %s" % [step[0], step[1]])


func test_lai_peak_does_not_carry_into_the_next_season() -> void:
	# Sowing maize again (stage 1) drops season one's 4.5 peak.
	var tiles: Array = [{"patch_idx": 0}]
	for peak: float in [4.5, 2.0]:
		for day: Array in [
			["planted", 0.0, 0.0], ["vegetative", peak, peak], ["maturity", 1.0, peak]
		]:
			var patch := {"crop_key": "maize", "crop_stage": day[0], "lai": day[1]}
			FarmTiles.write_patch(patch, 0, tiles)
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
	FarmLayout.assign_tiles(ScenarioCatalog.default_patches(), tiles, mats, 6)
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
