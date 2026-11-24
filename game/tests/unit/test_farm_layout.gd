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


func test_patches_from_game_reads_field_1() -> void:
	var patch := {"patch_idx": 0, "soil_profile_key": "sandy_subsaharan"}
	assert_eq(FarmLayout.patches_from_game({"fields": {"field_1": [patch]}}), [patch])
	assert_eq(FarmLayout.patches_from_game({"fields": {"other": [patch]}}), [])
	assert_eq(FarmLayout.patches_from_game({}), [])
