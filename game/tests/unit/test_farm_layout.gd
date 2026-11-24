extends GutTest
## FarmLayout: patch list -> column bands and soil textures (#516).


func _columns(patch_count: int) -> Array:
	var out: Array = []
	for col in range(6):
		out.append(FarmLayout.patch_for_column(col, patch_count, 6))
	return out


func test_bands_split_six_columns_contiguously() -> void:
	assert_eq(_columns(1), [0, 0, 0, 0, 0, 0], "one patch fills all six")
	assert_eq(_columns(2), [0, 0, 0, 1, 1, 1], "two patches: 3+3")
	assert_eq(_columns(3), [0, 0, 1, 1, 2, 2], "three patches: 2+2+2")
	assert_eq(_columns(0), [0, 0, 0, 0, 0, 0], "no patches: degenerate, in range")


func test_texture_follows_soil_key() -> void:
	assert_eq(FarmLayout.texture_for_soil_key("sandy_subsaharan"), "sandy")
	assert_eq(FarmLayout.texture_for_soil_key("clay_netherlands"), "clay")
	assert_eq(FarmLayout.texture_for_soil_key("loam_temperate"), "organic")
	assert_eq(FarmLayout.texture_for_soil_key("peat_cool_wet"), "organic")
	for key: String in FarmLayout.SOIL_TEXTURES:
		assert_true(FarmLayout.SOIL_TEXTURES[key].has("albedo"), "%s albedo" % key)


func test_assign_tiles_default_scenario_matches_historic_bands() -> void:
	# The default scenario must render exactly as before #516.
	var tiles: Array = []
	var mats: Array = []
	for col in range(6):
		tiles.append({"col": col})
		mats.append(ShaderMaterial.new())
	FarmLayout.assign_tiles(ScenarioCatalog.default_patches(), tiles, mats, 6)
	var soils: Array = tiles.map(func(t: Dictionary) -> String: return t["soil_type"])
	var idxs: Array = tiles.map(func(t: Dictionary) -> int: return t["patch_idx"])
	assert_eq(soils, ["sandy", "sandy", "organic", "organic", "clay", "clay"])
	assert_eq(idxs, [0, 0, 1, 1, 2, 2])
	var tex: Texture2D = mats[5].get_shader_parameter("albedo_texture")
	assert_eq(tex.resource_path, FarmLayout.SOIL_TEXTURES["clay"]["albedo"])


func test_soil_label_prefers_the_api_name_over_the_texture_class() -> void:
	var tile := {"soil_type": "organic", "soil_name": "Loam - Temperate"}
	assert_eq(FarmLayout.soil_label(tile), "Loam - Temperate")
	assert_eq(FarmLayout.soil_label({"soil_type": "clay", "soil_name": ""}), "clay", "old payload")
	assert_eq(FarmLayout.soil_label({}), "")


func test_assign_tiles_records_each_patchs_soil_name() -> void:
	var patches: Array = [
		{"soil_profile_key": "sandy_temperate", "soil_name": "Sandy - Temperate"},
		{"soil_profile_key": "loam_temperate", "soil_name": "Loam - Temperate"},
	]
	var tiles: Array = [{"col": 0}, {"col": 5}]
	FarmLayout.assign_tiles(patches, tiles, [ShaderMaterial.new(), ShaderMaterial.new()], 6)
	assert_eq(tiles[0]["soil_name"], "Sandy - Temperate")
	assert_eq(tiles[1]["soil_name"], "Loam - Temperate")
	assert_eq(tiles[1]["soil_type"], "organic", "texture class stays internal")


func test_assign_tiles_ignores_empty_layout() -> void:
	var tiles: Array = [{"col": 0, "soil_type": "clay", "patch_idx": 2}]
	FarmLayout.assign_tiles([], tiles, [ShaderMaterial.new()], 6)
	assert_eq(tiles[0]["patch_idx"], 2, "tiles untouched")


func test_fields_from_game_reads_every_field_in_key_order() -> void:
	# #600: every field, not only field_1, in the response's key order.
	var patch := {"patch_idx": 0, "soil_profile_key": "sandy_subsaharan"}
	var field_1 := {"field_id": "field_1", "patches": [patch]}
	assert_eq(FarmLayout.fields_from_game({"fields": {"field_1": [patch]}}), [field_1])
	var other := {"field_id": "other", "patches": [patch]}
	assert_eq(FarmLayout.fields_from_game({"fields": {"other": [patch]}}), [other])
	assert_eq(FarmLayout.fields_from_game({}), [])
	var body := '{"fields": {"south": [], "north": [{"crop_key": "rice"}], "east": []}}'
	var ids: Array = FarmLayout.fields_from_game(JSON.parse_string(body)).map(
		func(f: Dictionary) -> String: return f["field_id"]
	)
	assert_eq(ids, ["south", "north", "east"], "the response's order, not sorted")


## Field 1 has three patches (sandy, loam, clay) and field 2 one rice patch on
## clay: the [3 patches, 1 patch] layout of #600.
func _two_fields() -> Array:
	var rice := {"soil_profile_key": "clay_temperate", "crop_key": "rice"}
	return [
		{"field_id": "field_1", "patches": ScenarioCatalog.default_patches()},
		{"field_id": "field_2", "patches": [rice]},
	]


## Lay `fields` out on 36 bare tiles, row-major, and return them.
func _laid_out(fields: Array) -> Array:
	var tiles: Array = []
	var mats: Array = []
	for i in range(36):
		tiles.append({"col": i % 6, "row": floori(i / 6.0)})
		mats.append(ShaderMaterial.new())
	FarmLayout.assign_fields(fields, tiles, mats, Vector2i(6, 6))
	return tiles


func _six(value: Variant) -> Array:
	return [value, value, value, value, value, value]


## `key` of each tile in row `row`.
func _row(tiles: Array, row: int, key: String) -> Array:
	return tiles.slice(row * 6, row * 6 + 6).map(func(t: Dictionary) -> Variant: return t[key])


func test_rows_band_across_fields_with_the_column_formula() -> void:
	var rows := func(n: int) -> Array:
		return range(6).map(func(r: int) -> int: return FarmLayout.field_for_row(r, n, 6))
	assert_eq(rows.call(1), [0, 0, 0, 0, 0, 0], "one field takes all six rows")
	assert_eq(rows.call(2), [0, 0, 0, 1, 1, 1], "two fields: 3+3")
	assert_eq(rows.call(3), [0, 0, 1, 1, 2, 2], "three fields: 2+2+2")


func test_three_and_one_patch_fields_map_tiles_by_field_and_patch() -> void:
	var tiles := _laid_out(_two_fields())
	for row in range(3):
		assert_eq(_row(tiles, row, "field_id"), _six("field_1"))
		assert_eq(_row(tiles, row, "patch_idx"), [0, 0, 1, 1, 2, 2], "row %d" % row)
		var soils := ["sandy", "sandy", "organic", "organic", "clay", "clay"]
		assert_eq(_row(tiles, row, "soil_type"), soils)
	for row in range(3, 6):
		assert_eq(_row(tiles, row, "field_id"), _six("field_2"))
		assert_eq(_row(tiles, row, "patch_idx"), [0, 0, 0, 0, 0, 0], "row %d" % row)
		assert_eq(_row(tiles, row, "soil_type"), _six("clay"))
	# Two fields' patch 0 are different tiles; tile_key tells them apart.
	assert_eq(FarmLayout.tiles_of("field_1", 0, tiles), [0, 1, 6, 7, 12, 13] as Array[int])
	var lower: Array[int] = []
	lower.assign(range(18, 36))
	assert_eq(FarmLayout.tiles_of("field_2", 0, tiles), lower, "rows 3-5")
	assert_eq(FarmLayout.tiles_of("field_1", 3, tiles), [] as Array[int], "no such patch")
	assert_eq(FarmLayout.tile_key(tiles[24]), FarmLayout.patch_key("field_2", 0))
	assert_ne(FarmLayout.tile_key(tiles[0]), FarmLayout.tile_key(tiles[24]))


func test_field_gap_separates_fields_and_keeps_the_grid_centred() -> void:
	assert_between(FarmLayout.FIELD_GAP, 0.2, 0.5, "a named gap of 0.2 to 0.5")
	# One field: exactly today's rows, 1.0 apart and centred (#516 positions).
	var one := FarmLayout.row_z(1, 6, 1.0)
	assert_eq(one, [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5] as Array[float], "today's positions")
	for n: int in [2, 3, 4, 6]:
		var z := FarmLayout.row_z(n, 6, 1.0)
		var total := 0.0
		for row in range(6):
			total += z[row]
			if row == 0:
				continue
			var boundary: bool = (
				FarmLayout.field_for_row(row, n, 6) != FarmLayout.field_for_row(row - 1, n, 6)
			)
			var step: float = 1.0 + (FarmLayout.FIELD_GAP if boundary else 0.0)
			assert_almost_eq(z[row] - z[row - 1], step, 1e-6, "%d fields, row %d" % [n, row])
		assert_almost_eq(total / 6.0, 0.0, 1e-6, "%d fields: mean z is 0" % n)


func test_a_layout_that_does_not_fit_names_why() -> void:
	var grid := Vector2i(6, 6)
	var patch := {"soil_profile_key": "loam_temperate"}
	var fields: Array = []
	for i in range(6):
		fields.append({"field_id": "field_%d" % (i + 1), "patches": [patch]})
	assert_eq(FarmLayout.layout_error(fields, grid), "", "six fields fit six rows")
	fields.append({"field_id": "field_7", "patches": [patch]})
	assert_eq(FarmLayout.layout_error(fields, grid), "7 fields, but the map has 6 rows")
	var seven: Array = [patch, patch, patch, patch, patch, patch, patch]
	var wide := [{"field_id": "wide", "patches": seven}]
	assert_eq(FarmLayout.layout_error(wide, grid), "wide has 7 patches; a field takes 1 to 6")
	wide[0]["patches"] = seven.slice(0, 6)
	assert_eq(FarmLayout.layout_error(wide, grid), "", "six patches fit six columns")
	var empty := [{"field_id": "empty", "patches": []}]
	assert_eq(FarmLayout.layout_error(empty, grid), "empty has 0 patches; a field takes 1 to 6")
