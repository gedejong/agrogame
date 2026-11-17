extends GutTest

const FarmView = preload("res://scripts/farm_view.gd")


func test_grid_dimensions() -> void:
	assert_eq(FarmView.GRID_COLS, 6, "Grid should be 6 columns")
	assert_eq(FarmView.GRID_ROWS, 6, "Grid should be 6 rows")


func test_soil_textures_defined() -> void:
	# Texture classes moved to FarmLayout with the patch layout (#516).
	assert_eq(FarmLayout.SOIL_TEXTURES.size(), 3, "3 soil textures")
	for soil_type: String in ["sandy", "organic", "clay"]:
		assert_true(
			FarmLayout.SOIL_TEXTURES.has(soil_type),
			"Textures defined for %s" % soil_type,
		)
		var paths: Dictionary = FarmLayout.SOIL_TEXTURES[soil_type]
		assert_true(paths.has("albedo"), "%s has albedo path" % soil_type)
		assert_true(paths.has("normal"), "%s has normal path" % soil_type)


func test_texture_files_exist() -> void:
	for soil_type: String in FarmLayout.SOIL_TEXTURES:
		var paths: Dictionary = FarmLayout.SOIL_TEXTURES[soil_type]
		for key: String in paths:
			var path: String = paths[key]
			assert_true(
				FileAccess.file_exists(path),
				"Texture %s/%s exists at %s" % [soil_type, key, path],
			)


func test_shader_file_exists() -> void:
	assert_true(
		FileAccess.file_exists("res://shaders/soil_tile.gdshader"),
		"Soil tile shader exists",
	)
