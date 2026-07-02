extends GutTest

const SoilViewScript = preload("res://scripts/soil_view.gd")


func test_layer_colors_defined() -> void:
	assert_true(SoilViewScript.LAYER_COLORS.has("sand"))
	assert_true(SoilViewScript.LAYER_COLORS.has("loam"))
	assert_true(SoilViewScript.LAYER_COLORS.has("clay"))


func test_profile_layers_sandy() -> void:
	var layers: Array = SoilViewScript.get_profile_layers("sandy")
	assert_eq(layers.size(), 3, "Sandy has 3 layers")
	assert_eq(layers[0]["texture"], "sand")


func test_profile_layers_clay() -> void:
	var layers: Array = SoilViewScript.get_profile_layers("clay")
	assert_eq(layers.size(), 3, "Clay has 3 layers")
	# Distinct horizons (#206): loamy A-horizon topsoil over clay B/C subsoil.
	assert_eq(layers[0]["texture"], "loam", "Topsoil A-horizon is loam")
	assert_eq(layers[1]["texture"], "clay", "Subsoil B-horizon is clay")


func test_profile_layers_organic() -> void:
	var layers: Array = SoilViewScript.get_profile_layers("organic")
	assert_eq(layers.size(), 3, "Organic/loam has 3 layers")
	assert_eq(layers[0]["texture"], "loam")


func test_constants() -> void:
	assert_gt(SoilViewScript.CUTAWAY_WIDTH, 0.0, "Cutaway width positive")
	assert_gt(SoilViewScript.SCALE_CM, 0.0, "Scale cm positive")


func test_show_cutaway_sets_active() -> void:
	var view := Node3D.new()
	view.set_script(SoilViewScript)
	add_child_autofree(view)
	var columns: Array[Dictionary] = [
		{
			"pos": Vector3.ZERO,
			"soil_state": {"water_theta": [0.2, 0.24, 0.22]},
			"profile": SoilViewScript.get_profile_layers("sandy"),
			"root_depth_cm": 0.0,
			"crop_key": "",
			"show_info": false,
		}
	]
	view.show_cutaway(columns)
	assert_true(view.is_active(), "Should be active after show")


func test_refresh_preserves_materials() -> void:
	var view := Node3D.new()
	view.set_script(SoilViewScript)
	add_child_autofree(view)
	var columns: Array[Dictionary] = [
		{
			"pos": Vector3.ZERO,
			"soil_state": {"water_theta": [0.2, 0.24, 0.22]},
			"profile": SoilViewScript.get_profile_layers("sandy"),
			"root_depth_cm": 0.0,
			"crop_key": "",
			"show_info": false,
		}
	]
	view.show_cutaway(columns)
	var mat_count: int = view._layer_materials.size()
	assert_eq(mat_count, 3, "3 layers = 3 materials")
	# Refresh with different water — materials should be reused
	var columns2: Array[Dictionary] = columns.duplicate(true)
	columns2[0]["soil_state"] = {"water_theta": [0.3, 0.28, 0.25]}
	view.show_cutaway(columns2)
	assert_eq(view._layer_materials.size(), mat_count, "Materials reused on refresh")


func test_refresh_rebuilds_roots() -> void:
	var view := Node3D.new()
	view.set_script(SoilViewScript)
	add_child_autofree(view)
	var columns: Array[Dictionary] = [
		{
			"pos": Vector3.ZERO,
			"soil_state": {"water_theta": [0.2, 0.24, 0.22]},
			"profile": SoilViewScript.get_profile_layers("sandy"),
			"root_depth_cm": 20.0,
			"crop_key": "maize",
			"show_info": false,
		}
	]
	view.show_cutaway(columns)
	# Roots are shader-based (#222): layer materials carry root_texture +
	# root_strength uniforms rather than separate tagged nodes.
	for mat: ShaderMaterial in view._layer_materials:
		assert_gt(
			float(mat.get_shader_parameter("root_strength")),
			0.0,
			"Root strength active when root_depth_cm > 0",
		)
		assert_not_null(mat.get_shader_parameter("root_texture"), "Root texture set")
	# Refresh with deeper roots — root uniforms should be rebuilt, still active.
	var columns2: Array[Dictionary] = columns.duplicate(true)
	columns2[0]["root_depth_cm"] = 40.0
	columns2[0]["soil_state"] = {"water_theta": [0.25, 0.26, 0.23]}
	view.show_cutaway(columns2)
	for mat: ShaderMaterial in view._layer_materials:
		assert_gt(
			float(mat.get_shader_parameter("root_strength")),
			0.0,
			"Root strength still active after refresh with deeper roots",
		)
