extends GutTest
## Wind data of the crop renderers: the per-plant frame stamped on every
## plant mesh's material and the wind-carrying materials.

const CR = preload("res://scripts/crop_renderer_3d.gd")
const VisualsRef = preload("res://scripts/crop_visuals.gd")


func test_organ_material_is_wind_shader_with_params() -> void:
	var mat := CR.create_organ_material(Color(0.5, 0.25, 0.125), 0.4, 0.6, 1.5)
	assert_true(mat is ShaderMaterial, "Organ material is a ShaderMaterial")
	assert_eq(mat.shader, CR.ORGAN_SHADER, "Organ shader")
	var albedo: Vector3 = mat.get_shader_parameter("albedo")
	assert_almost_eq(albedo.x, 0.5, 0.001, "Albedo r")
	assert_almost_eq(albedo.z, 0.125, 0.001, "Albedo b")
	assert_almost_eq(float(mat.get_shader_parameter("roughness")), 0.4, 0.001, "Roughness")
	assert_almost_eq(float(mat.get_shader_parameter("sway")), 0.6, 0.001, "Sway")
	assert_almost_eq(float(mat.get_shader_parameter("wind_phase")), 1.5, 0.001, "Phase")


func test_organ_material_defaults_and_phase_wrap() -> void:
	var mat := CR.create_organ_material(Color.WHITE)
	assert_almost_eq(float(mat.get_shader_parameter("sway")), 1.0, 0.001, "Free swing by default")
	var wrapped := CR.create_organ_material(Color.WHITE, 0.75, 1.0, TAU + 0.5)
	assert_almost_eq(float(wrapped.get_shader_parameter("wind_phase")), 0.5, 0.001, "Phase wraps")


func test_fixture_material_is_static() -> void:
	var mat := CR.create_fixture_material(Color.RED, 0.9)
	assert_true(mat is StandardMaterial3D, "Fixtures are not wind-driven")
	assert_almost_eq(mat.roughness, 0.9, 0.001, "Roughness")
	assert_eq(mat.cull_mode, BaseMaterial3D.CULL_DISABLED, "Double-sided")


func test_stem_material_colours() -> void:
	var fresh := Color(0.1, 0.6, 0.2)
	var dry := Color(0.5, 0.4, 0.2)
	var c: Vector3 = CR.create_stem_material(0.0, fresh, dry).get_shader_parameter("stem_color")
	assert_almost_eq(c.y, 0.6, 0.001, "Fresh colour at zero senescence")
	var d: Vector3 = CR.create_stem_material(1.0, fresh, dry).get_shader_parameter("stem_color")
	assert_almost_eq(d.x, 0.5, 0.001, "Dry colour at full senescence")
	var e: Vector3 = CR.create_stem_material(0.0).get_shader_parameter("stem_color")
	assert_almost_eq(e.x, CR.STEM_COLOR.r, 0.001, "Default fresh colour is the culm green")


func test_leaf_material_hanging_flag() -> void:
	var grape := CR.create_leaf_material("grape", 0.0, {})
	var maize := CR.create_leaf_material("maize", 0.0, {})
	assert_almost_eq(float(grape.get_shader_parameter("hanging")), 1.0, 0.001, "Vine leaf hangs")
	assert_almost_eq(float(maize.get_shader_parameter("hanging")), 0.0, 0.001, "Blade from collar")


func test_leaf_quad_origin_is_the_attachment() -> void:
	var leaf := CR.create_leaf_quad(0.2, 0.2, Vector3(0, -0.09, 0), Vector3.ZERO)
	autofree(leaf)
	assert_eq(leaf.position, Vector3.ZERO, "Node origin stays at the hinge")
	var aabb: AABB = leaf.mesh.get_aabb()
	assert_almost_eq(aabb.end.y, 0.01, 0.001, "Quad top just above the hinge")
	assert_almost_eq(aabb.position.y, -0.19, 0.001, "Quad hangs below the hinge")


func test_stamp_wind_frame_sets_heights_and_flex() -> void:
	var plant := Node3D.new()
	add_child_autofree(plant)
	var stem := CR.attach_mesh(
		plant,
		CR.create_stem_mesh(1.0, 0.02, 0.01),
		CR.create_stem_material(0.0),
		Vector3(0, 0.5, 0)
	)
	var pivot := Node3D.new()
	pivot.position = Vector3(0, 0.8, 0)
	plant.add_child(pivot)
	var leaf := CR.attach_mesh(
		pivot,
		CR.build_curved_leaf(0.5, 0.05, 0.3, 4, 0.0, 0.1, CR.LeafShape.new()),
		CR.create_leaf_material("maize", 0.0, {}),
		Vector3.ZERO
	)
	CR.stamp_wind_frame(plant, 0.35, 0.42)
	var stem_mat: ShaderMaterial = stem.material_override
	var leaf_mat: ShaderMaterial = leaf.material_override
	var height: float = stem_mat.get_shader_parameter("plant_height")
	assert_gte(height, 1.0, "Plant height reaches the stem top")
	assert_eq(leaf_mat.get_shader_parameter("plant_height"), height, "Same height on all")
	var stem_origin: float = stem_mat.get_shader_parameter("origin_height")
	assert_almost_eq(stem_origin, 0.5, 0.001, "Stem origin at half its height")
	var leaf_origin: float = leaf_mat.get_shader_parameter("origin_height")
	assert_almost_eq(leaf_origin, 0.8, 0.001, "Leaf origin at its node")
	assert_almost_eq(float(leaf_mat.get_shader_parameter("plant_flex")), 0.35, 0.001, "Flex")
	assert_almost_eq(float(stem_mat.get_shader_parameter("plant_jitter")), 0.42, 0.001, "Jitter")
	assert_almost_eq(float(leaf_mat.get_shader_parameter("plant_jitter")), 0.42, 0.001, "Same")


func test_stamp_wind_frame_reports_a_material_shared_across_heights() -> void:
	var plant := Node3D.new()
	add_child_autofree(plant)
	var shared := CR.create_stem_material(0.0)
	var mesh := CR.create_stem_mesh(0.4, 0.02, 0.02)
	var low := CR.attach_mesh(plant, mesh, shared, Vector3(0, 0.2, 0))
	var twin := CR.attach_mesh(plant, mesh, shared, Vector3(0.1, 0.2, 0))
	var high := CR.attach_mesh(plant, mesh, shared, Vector3(0, 0.6, 0))
	var fixture := CR.attach_mesh(plant, mesh, CR.create_fixture_material(Color.RED), Vector3.ZERO)
	CR.stamp_wind_frame(plant, 1.0, 0.1)
	assert_push_error("shares its material")
	assert_push_error_count(1, "Sharing a material at one height is fine")
	assert_eq(low.material_override, shared, "Nothing is copied")
	assert_eq(twin.material_override, shared, "Nothing is copied")
	assert_eq(high.material_override, shared, "Nothing is copied")
	var origin: float = shared.get_shader_parameter("origin_height")
	assert_almost_eq(origin, 0.2, 0.001, "The first mesh's origin stands")
	assert_true(fixture.material_override is StandardMaterial3D, "Fixtures are left alone")


func test_plants_carry_their_own_wind_jitter() -> void:
	var seen: Array[float] = []
	for seed_val: int in [7, 8, 9]:
		var plant := VisualsRef.create_3d_plant("maize", 0.9, 0.1, {}, 0.6, seed_val)
		add_child_autofree(plant)
		var mat: ShaderMaterial = _first_wind_material(plant)
		assert_not_null(mat, "Plant has wind-driven meshes")
		var jitter: float = mat.get_shader_parameter("plant_jitter")
		assert_gte(jitter, 0.0, "Jitter in range")
		assert_lt(jitter, 1.0, "Jitter in range")
		assert_false(seen.has(jitter), "Each plant draws its own jitter")
		seen.append(jitter)


func test_every_crop_plant_is_stamped_consistently() -> void:
	## Every wind-driven mesh of every crop, at stages from seedling to ripe,
	## carries its own origin height: no renderer shares a material between
	## meshes standing at different heights.
	for crop_key: String in ["maize", "spring_wheat", "sorghum", "rice", "grape"]:
		var expected_flex: float = VisualsRef.PLANT_FLEX[crop_key]
		for stage: Array in [[0.3, 0.0, 0.0], [0.9, 0.1, 0.1], [1.0, 0.8, 0.7]]:
			var plant := VisualsRef.create_3d_plant(crop_key, stage[0], stage[2], {}, stage[1], 7)
			add_child_autofree(plant)
			var meshes: Array[Dictionary] = []
			VisualsRef.collect_meshes(plant, Transform3D(), meshes)
			var label: String = "%s at %s" % [crop_key, stage]
			assert_gt(meshes.size(), 0, label + " has meshes")
			var wind_meshes: int = 0
			for entry: Dictionary in meshes:
				var mat: ShaderMaterial = entry["material"] as ShaderMaterial
				if mat == null:
					continue
				wind_meshes += 1
				var h: float = mat.get_shader_parameter("plant_height")
				assert_gt(h, 0.0, label + " plant height positive")
				var origin: float = mat.get_shader_parameter("origin_height")
				assert_gte(h + 1e-4, origin, label + " origin below top")
				var own_origin: float = maxf((entry["transform"] as Transform3D).origin.y, 0.0)
				assert_almost_eq(
					origin, own_origin, 1e-4, label + " mesh origin on its own material"
				)
				var flex: float = mat.get_shader_parameter("plant_flex")
				assert_almost_eq(flex, expected_flex, 1e-4, label + " flex")
			assert_gt(wind_meshes, 0, label + " has wind-driven meshes")
	assert_push_error_count(0, "No renderer shares a material across heights")


func test_baked_layers_carry_wind_params() -> void:
	var container := Node3D.new()
	add_child_autofree(container)
	VisualsRef._build_baked_plants(
		container, "spring_wheat", Vector2i(4, 4), 0, 0, 1.0, 0.9, 0.1, {}, 0.6, 1.0
	)
	var layers: int = 0
	for child: Node in container.get_children():
		if not child is MultiMeshInstance3D:
			continue
		var mmi := child as MultiMeshInstance3D
		var mat: ShaderMaterial = mmi.material_override as ShaderMaterial
		if mat == null:
			continue
		layers += 1
		var h: Variant = mat.get_shader_parameter("plant_height")
		assert_not_null(h, "Baked layer's material carries the plant height")
		assert_gt(float(h), 0.0, "Positive plant height")
		assert_almost_eq(float(mat.get_shader_parameter("plant_flex")), 1.0, 1e-4, "Wheat flex")
		assert_almost_eq(
			float(mat.get_shader_parameter("plant_jitter")), 0.0, 1e-6, "No own jitter"
		)
		assert_true(mmi.multimesh.use_custom_data, "Plants carry their jitter as custom data")
		assert_gt(mmi.multimesh.instance_count, 0, "Layer draws this variant's plants")
	assert_gt(layers, 0, "Wind-driven baked layers were created")


func test_crop_shaders_declare_no_instance_uniforms() -> void:
	# The engine keeps instance uniforms in one buffer sized for a few
	# thousand geometry instances; a farm of stands is drawn by more mesh
	# layers than that, so the wind frame rides on materials and custom data.
	var pattern := RegEx.create_from_string("(?m)^\\s*instance\\s+uniform")
	for path: String in [
		"res://shaders/crop_wind.gdshaderinc",
		"res://shaders/crop_leaf.gdshader",
		"res://shaders/crop_stem.gdshader",
		"res://shaders/crop_organ.gdshader",
	]:
		var text: String = FileAccess.get_file_as_string(path)
		assert_false(text.is_empty(), path + " is readable")
		assert_null(pattern.search(text), path + " declares no instance uniforms")


func _first_wind_material(plant: Node) -> ShaderMaterial:
	for node: Node in plant.find_children("*", "MeshInstance3D", true, false):
		var mat: ShaderMaterial = (node as MeshInstance3D).material_override as ShaderMaterial
		if mat != null:
			return mat
	return null
