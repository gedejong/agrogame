extends GutTest

const FarmView3D = preload("res://scripts/farm_view_3d.gd")


func test_grid_dimensions() -> void:
	assert_eq(FarmView3D.GRID_COLS, 6, "Grid should be 6 columns")
	assert_eq(FarmView3D.GRID_ROWS, 6, "Grid should be 6 rows")


func test_soil_types_defined() -> void:
	assert_eq(FarmView3D.SOIL_TYPES.size(), 3, "3 soil types")
	assert_has(FarmView3D.SOIL_TYPES, "sandy")
	assert_has(FarmView3D.SOIL_TYPES, "organic")
	assert_has(FarmView3D.SOIL_TYPES, "clay")


func test_soil_type_for_columns() -> void:
	assert_eq(FarmView3D._soil_type_for(0), "sandy", "Col 0 = sandy")
	assert_eq(FarmView3D._soil_type_for(1), "sandy", "Col 1 = sandy")
	assert_eq(FarmView3D._soil_type_for(2), "organic", "Col 2 = organic")
	assert_eq(FarmView3D._soil_type_for(3), "organic", "Col 3 = organic")
	assert_eq(FarmView3D._soil_type_for(4), "clay", "Col 4 = clay")
	assert_eq(FarmView3D._soil_type_for(5), "clay", "Col 5 = clay")


func test_soil_textures_defined() -> void:
	for soil_type: String in FarmView3D.SOIL_TYPES:
		assert_true(
			FarmView3D.SOIL_TEXTURES.has(soil_type),
			"Textures defined for %s" % soil_type,
		)
		var paths: Dictionary = FarmView3D.SOIL_TEXTURES[soil_type]
		assert_true(paths.has("albedo"), "%s has albedo path" % soil_type)
		assert_true(paths.has("normal"), "%s has normal path" % soil_type)


func test_texture_files_exist() -> void:
	for soil_type: String in FarmView3D.SOIL_TYPES:
		var paths: Dictionary = FarmView3D.SOIL_TEXTURES[soil_type]
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
