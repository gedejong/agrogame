extends GutTest
## DioramaRegions (#652): the regional stacks as data (criterion 1) and their
## wiring into the slab (criterion 2): one regional material per slab on every
## extension quad, its fill per quad, every set at its real-world size, and the
## placeholder kept for an unknown climate key.

const FarmViewScene = preload("res://scenes/farm_view.tscn")
const KENYA_TWO_FIELDS := 6  # ScenarioCatalog ids, as in test_diorama_slab.gd
const SAHEL := 2
## The #652 table: [name, top m, bottom m, set, size m] per layer.
const TABLE := {
	"netherlands_temperate":
	[
		["Holocene marine clay", 0.0, 2.2, "brown_mud", 1.30],
		["Basal peat", 2.2, 2.8, "mud_forest", 2.35],
		["Pleistocene cover sand", 2.8, INF, "sand_01", 1.50],
	],
	"kenya_highlands":
	[
		["Red clay subsoil (nitic)", 0.0, 2.6, "red_mud_stones", 1.50],
		["Saprolite of weathered volcanic rock", 2.6, INF, "rock_face", 2.38],
	],
	"sahel_arid":
	[
		["Aeolian sand", 0.0, 1.6, "gravelly_sand", 2.48],
		["Ironstone gravel", 1.6, 2.2, "red_laterite_soil_stones", 2.00],
		["Ferricrete", 2.2, 2.8, "rock_face", 2.38],
		["Mottled and pallid zone", 2.8, INF, "dense_sand", 1.80],
	],
}


func test_layers_pin_the_table_for_every_climate() -> void:
	for key: String in TABLE:
		var got: Array = DioramaRegions.layers_for(key).map(
			func(l: Dictionary) -> Array:
				return [l["name"], l["top_m"], l["bottom_m"], l["set"], l["size_m"]]
		)
		assert_eq(got, TABLE[key], key)


func test_unknown_climate_has_no_stack_and_no_material() -> void:
	assert_eq(DioramaRegions.layers_for("atlantis"), [])
	assert_null(DioramaRegions.material("atlantis", 0.5))


func test_material_carries_the_stack_and_its_artefact_set() -> void:
	var mat := DioramaRegions.material("sahel_arid", 0.5)
	var diff: Array = mat.get_shader_parameter("set_diff")
	var paths: Array = diff.map(func(t: Texture2D) -> String: return t.resource_path)
	var want: Array = ["gravelly_sand", "red_laterite_soil_stones", "rock_face", "dense_sand"]
	want.append("red_laterite_soil_stones")
	assert_eq(paths, want.map(func(s: String) -> String: return DioramaRegions.map_path(s, "diff")))
	_assert_floats(mat.get_shader_parameter("layer_bottom_m"), [1.6, 2.2, 2.8], "Sahel")
	var nor: Array = mat.get_shader_parameter("set_nor_gl")
	assert_eq(nor[1].resource_path, DioramaRegions.map_path("red_laterite_soil_stones", "nor_gl"))
	var kenya := DioramaRegions.material("kenya_highlands", 0.5)
	var deep := DioramaRegions.DEEP_M
	_assert_floats(kenya.get_shader_parameter("layer_bottom_m"), [2.6, deep, deep], "unused: deep")
	var arm: Array = kenya.get_shader_parameter("set_arm")
	assert_eq(arm[4].resource_path, DioramaRegions.map_path("rock_wall_08", "arm"), "corestones")


## Packed float32 `got` against `want`, element by element.
func _assert_floats(got: PackedFloat32Array, want: Array, label: String) -> void:
	assert_eq(got.size(), want.size(), label)
	for i in range(mini(got.size(), want.size())):
		assert_almost_eq(got[i], want[i], 1e-5, "%s [%d]" % [label, i])


## A slab laid out for `fields` on a 6x6 grid, under the farm view's sun turned
## a further `turn_deg` about y (as test_diorama_slab.gd builds it).
func _slab(fields: Array, turn_deg: float = 0.0) -> DioramaSlab:
	var root := Node3D.new()
	add_child_autofree(root)
	var tiles := Node3D.new()
	var crops := Node3D.new()
	root.add_child(tiles)
	root.add_child(crops)
	var grid := FarmTiles.build_grid(tiles, crops, Vector2i(6, 6), 1.0)
	FarmLayout.assign_fields(fields, grid["tile_data"], grid["materials"], Vector2i(6, 6))
	var row_z := FarmLayout.row_z(fields.size(), 6, 1.0)
	for i in range(36):
		grid["meshes"][i].position.z = row_z[grid["tile_data"][i]["row"]]
	var view: Node3D = FarmViewScene.instantiate()
	var sun := DirectionalLight3D.new()
	sun.transform = (view.get_node("DirectionalLight3D") as Node3D).transform
	view.free()
	sun.rotate_y(deg_to_rad(turn_deg))
	root.add_child(sun)
	var slab := DioramaSlab.new()
	root.add_child(slab)
	slab.lay_out(fields, grid["tile_data"], grid["meshes"], sun)
	return slab


## A /step `patches` payload: every patch on a 100 cm loam profile.
func _patches(fields: Array) -> Dictionary:
	var soil := {
		"layer_thickness_cm": [25.0, 35.0, 40.0],
		"texture": ["loam", "loam", "loam"],
		"soc_pct": [1.0, 1.0, 1.0],
		"water_theta": [0.2, 0.2, 0.2],
		"field_capacity": [0.25, 0.25, 0.25],
		"wilting_point": [0.12, 0.12, 0.12],
	}
	var out := {}
	for field: Dictionary in fields:
		out[field["field_id"]] = field["patches"].map(
			func(_p: Dictionary) -> Dictionary: return {"root_depth_cm": 30.0, "soil_state": soil}
		)
	return out


func test_slab_puts_one_regional_material_on_every_extension_quad() -> void:
	for id: int in [ScenarioCatalog.DEFAULT_ID, SAHEL, KENYA_TWO_FIELDS]:
		var fields := ScenarioCatalog.fields_for(id)
		var slab := _slab(fields)
		var first: Material = slab._extensions[0]["mesh"].material_override
		assert_same(first, slab._extensions[0]["placeholder"], "placeholder until the payload")
		slab.update(_patches(fields))
		var regional: ShaderMaterial = slab._extensions[0]["mesh"].material_override
		assert_eq(regional.shader, DioramaRegions.SHADER, ScenarioCatalog.label_for(id))
		for ext: Dictionary in slab._extensions:
			assert_same(ext["mesh"].material_override, regional, "one material, no break")
		assert_eq(regional.get_shader_parameter("wu_per_m"), DioramaSlab.WU_PER_CM * 100.0)
		assert_almost_eq(regional.get_shader_parameter("profile_bottom_m"), 1.0, 1e-6)
		assert_gt(regional.get_shader_parameter("artefact_count"), 0, "artefacts placed")


func test_every_set_repeats_at_its_real_world_size() -> void:
	var fields := ScenarioCatalog.default_fields()
	var slab := _slab(fields)
	slab.update(_patches(fields))
	var mat: ShaderMaterial = slab._extensions[0]["mesh"].material_override
	var sizes: PackedFloat32Array = mat.get_shader_parameter("set_size_m")
	var wu_per_m: float = mat.get_shader_parameter("wu_per_m")
	# Poly Haven's scanned sides: brown_mud, mud_forest, sand_01 (sand_01 pads
	# the empty fourth slot), and the sandy_gravel lenses.
	var want_m := [1.30, 2.35, 1.50, 1.50, 2.10]
	for i in range(5):
		var repeat_wu: float = sizes[i] * wu_per_m  # one texture tile in world units
		assert_almost_eq(repeat_wu / (want_m[i] * 0.5), 1.0, 0.1, "slot %d within 10 %%" % i)


func test_each_quad_carries_its_own_fill() -> void:
	for turn: float in [0.0, 180.0]:
		var fields := ScenarioCatalog.default_fields()
		var slab := _slab(fields, turn)
		slab.update(_patches(fields))
		var fills := []
		for ext: Dictionary in slab._extensions:
			var mesh: MeshInstance3D = ext["mesh"]
			assert_eq(mesh.get_instance_shader_parameter("face_fill"), slab._fill(mesh))
			fills.append(mesh.get_instance_shader_parameter("face_fill"))
		fills.sort()
		assert_eq(fills, [0.0, DioramaSlab.FACE_FILL], "sun turned %d" % turn)


func test_unknown_climate_keeps_the_placeholder() -> void:
	var fields := ScenarioCatalog.default_fields().duplicate(true)
	for patch: Dictionary in fields[0]["patches"]:
		patch["climate_key"] = "atlantis"
	var slab := _slab(fields)
	slab.update(_patches(fields))
	for ext: Dictionary in slab._extensions:
		assert_same(ext["mesh"].material_override, ext["placeholder"])
		assert_true(ext["mesh"].visible)


func test_stones_stay_put_over_two_seasons_and_a_reload() -> void:
	var fields := ScenarioCatalog.fields_for(1)  # Kenya-highland maize
	var slab := _slab(fields)
	slab.update(_patches(fields))
	var regional: ShaderMaterial = slab._extensions[0]["mesh"].material_override
	var placed: Image = regional.get_shader_parameter("artefacts").get_image()
	var soil: Dictionary = _patches(fields)["field_1"][0]["soil_state"]
	for week in range(104):  # two years of weekly payloads, wetting and drying
		var theta := 0.13 + 0.12 * absf(sin(week * 0.3))
		soil["water_theta"] = [theta, theta, theta]
		slab.update({"field_1": [{"root_depth_cm": week % 52 * 2.0, "soil_state": soil}]})
	for ext: Dictionary in slab._extensions:
		assert_same(ext["mesh"].material_override, regional, "the same material")
	var after: Image = regional.get_shader_parameter("artefacts").get_image()
	assert_eq(after.get_data(), placed.get_data(), "no artefact moved")
	var reloaded := _slab(fields)  # a saved game laid out again
	reloaded.update(_patches(fields))
	var again: ShaderMaterial = reloaded._extensions[0]["mesh"].material_override
	assert_eq(again.get_shader_parameter("artefacts").get_image().get_data(), placed.get_data())
