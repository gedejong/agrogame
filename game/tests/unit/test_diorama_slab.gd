extends GutTest
## DioramaSlab (#646): segments per edge tile mapped by (field, patch)
## (criterion 4), the true-scale section and its 4x extension, hidden faces
## until a payload (5), framing (7) and the extension hook (13). #680 replaced
## criterion 14's fill with no fill, and gave the faces their soil's cited hue.
## The farm view tests at the end check the wiring: every /step result
## refreshes the slab and clicks still reach tiles.

const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")
## Layer thicknesses (cm) of the catalog's soils, from data/soils/presets.yaml.
const LAYERS := {
	"sandy_temperate": [25.0, 35.0, 40.0],
	"loam_temperate": [25.0, 35.0, 40.0],
	"clay_temperate": [30.0, 35.0, 40.0],
	"clay_netherlands": [30.0, 35.0, 40.0],
	"sandy_subsaharan": [20.0, 40.0, 50.0],
}
const KENYA_TWO_FIELDS := 6  # ScenarioCatalog id of the maize-and-wheat farm (#658)
const SAHEL := 2

var _auto_soil_view: bool


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_soil_view = ProjectSettings.get_setting("agrogame/debug/auto_soil_view", false)
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", _auto_soil_view)
	GameState.game_id = ""


## A slab laid out for `fields` on a 6x6 grid.
func _slab(fields: Array) -> DioramaSlab:
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
	var slab := DioramaSlab.new()
	root.add_child(slab)
	slab.lay_out(fields, grid["tile_data"], grid["meshes"])
	return slab


## A soil_state on `thickness`: loam, 1 % SOC, theta 0.2, FC 0.25, WP 0.12.
func _soil(thickness: Array, theta: float = 0.2) -> Dictionary:
	var soil := {"layer_thickness_cm": thickness}
	var per_layer := {
		"texture": "loam",
		"soc_pct": 1.0,
		"water_theta": theta,
		"field_capacity": 0.25,
		"wilting_point": 0.12,
	}
	for key: String in per_layer:
		soil[key] = []
		for _t: float in thickness:
			soil[key].append(per_layer[key])
	return soil


## A /step result's `patches` for `fields`, each patch on its preset's layers.
func _patches(fields: Array, theta: float = 0.2) -> Dictionary:
	var out := {}
	for field: Dictionary in fields:
		var plist: Array = []
		for patch: Dictionary in field["patches"]:
			var soil := _soil(LAYERS[patch["soil_profile_key"]], theta)
			plist.append({"root_depth_cm": 30.0, "soil_state": soil})
		out[field["field_id"]] = plist
	return out


func _side(slab: DioramaSlab, side: String) -> Array[Dictionary]:
	return slab._segments.filter(func(s: Dictionary) -> bool: return s["side"] == side)


## The y extent of `mesh` in the slab's space, as (top, bottom).
func _span(mesh: MeshInstance3D) -> Vector2:
	var box := mesh.transform * mesh.get_aabb()
	return Vector2(box.end.y, box.position.y)


func test_netherlands_default_has_a_segment_per_edge_tile() -> void:
	var slab := _slab(ScenarioCatalog.default_fields())
	var on_x := _side(slab, "+x")
	var on_z := _side(slab, "+z")
	assert_eq(on_x.size(), 6, "+x segments")
	assert_eq(on_z.size(), 6, "+z segments")
	for seg: Dictionary in on_z:
		var col: int = seg["tile"].x
		var want := ["field_1", FarmLayout.patch_for_column(col, 3, 6), 5]
		assert_eq([seg["field_id"], seg["patch_idx"], seg["tile"].y], want, "+z col %d" % col)
	for seg: Dictionary in on_x:
		assert_eq([seg["field_id"], seg["patch_idx"], seg["tile"].x], ["field_1", 2, 5])


func test_two_fields_are_two_blocks_with_a_gap() -> void:
	var slab := _slab(ScenarioCatalog.fields_for(KENYA_TWO_FIELDS))
	var rows := {}
	for seg: Dictionary in _side(slab, "+x"):
		rows[seg["tile"].y] = seg
		var want := ["field_1", 0] if seg["tile"].y < 3 else ["field_2", 0]
		assert_eq([seg["field_id"], seg["patch_idx"]], want, "+x row %d" % seg["tile"].y)
	var z_rows: Array = _side(slab, "+z").map(func(s: Dictionary) -> int: return s["tile"].y)
	assert_eq(z_rows.count(2) + z_rows.count(5), 12, "+z faces under rows 2 and 5 only")
	var gap: float = rows[3]["mesh"].position.z - rows[2]["mesh"].position.z - 1.0
	assert_almost_eq(gap, 0.3, 1e-5, "the field gap between rows 2 and 3")
	assert_eq(slab._extensions.size(), 4, "one extension per block and side")


func test_faces_hang_from_the_surface_at_true_scale() -> void:
	for scenario: Array in [[ScenarioCatalog.DEFAULT_ID, 0.525, 2.1], [SAHEL, 0.55, 2.2]]:
		var fields := ScenarioCatalog.fields_for(scenario[0])
		var slab := _slab(fields)
		slab.update(_patches(fields))
		assert_almost_eq(slab.section_depth_wu(), scenario[1], 1e-5, "section")
		assert_almost_eq(slab.total_depth_wu(), scenario[2], 1e-5, "with the extension")
		for seg: Dictionary in slab._segments:
			assert_almost_eq(_span(seg["mesh"]), Vector2(0.0, -scenario[1]), Vector2.ONE * 1e-5)
		for ext: Dictionary in slab._extensions:
			var span := _span(ext["mesh"])
			assert_almost_eq(span, Vector2(-scenario[1], -scenario[2]), Vector2.ONE * 1e-5)
		for side: Dictionary in slab._sides:
			assert_almost_eq(_span(side["mesh"]).y, -scenario[2], 1e-5, "closed to the bottom")


func test_no_face_takes_clicks() -> void:
	var slab := _slab(ScenarioCatalog.default_fields())
	assert_eq(slab.find_children("*", "CollisionObject3D", true, false), [])


func test_faces_stay_hidden_until_their_payload() -> void:
	var fields := ScenarioCatalog.default_fields()
	var slab := _slab(fields)
	var shown := func() -> int:
		return slab._segments.filter(func(s: Dictionary) -> bool: return s["mesh"].visible).size()
	slab.update({})
	slab.update({"field_1": [{"soil_state": {"water_theta": [0.2]}}, {"soil_state": null}]})
	assert_eq(shown.call(), 0, "no layout yet: hidden, without an error")
	var patches := _patches(fields)
	patches["field_1"][1] = {"root_depth_cm": 10.0}
	slab.update(patches)
	assert_eq(shown.call(), 10, "the loam patch's two +z segments wait for their payload")
	slab.update(_patches(fields))
	assert_eq(shown.call(), 12)


func test_placeholder_continues_each_segments_deepest_layer() -> void:
	var fields := ScenarioCatalog.default_fields()
	var slab := _slab(fields)
	var patches := _patches(fields)
	patches["field_1"][0]["soil_state"]["water_theta"] = [0.2, 0.2, 0.05]
	slab.update(patches)
	var plus_z := func(e: Dictionary) -> bool: return e["mesh"].rotation_degrees.y == 0.0
	var on_z: Dictionary = slab._extensions.filter(plus_z)[0]
	var tex: Texture2D = (on_z["placeholder"] as ShaderMaterial).get_shader_parameter("profile_tex")
	var img := tex.get_image()
	assert_eq(img.get_size(), Vector2i(6, 1))
	var dry := SoilFaceColour.layer_scale(patches["field_1"][0]["soil_state"], 2)
	var moist := SoilFaceColour.layer_scale(patches["field_1"][2]["soil_state"], 2)
	for x in range(6):
		# UV.x runs with world x on the +z face: sandy under columns 0-1.
		assert_almost_eq(img.get_pixel(x, 0).r, dry if x < 2 else moist, 1e-5, "slot %d" % x)
		assert_eq(img.get_pixel(x, 0).g, 0.0, "no roots below the section")


func test_extension_hook_replaces_only_the_placeholder() -> void:
	var fields := ScenarioCatalog.default_fields()
	var slab := _slab(fields)
	var regional := ShaderMaterial.new()
	regional.shader = DioramaSlab.FACE_SHADER
	slab.set_extension_material(regional)
	slab.update(_patches(fields))
	for ext: Dictionary in slab._extensions:
		assert_same(ext["mesh"].material_override, regional, "extension carries the hook's")
	assert_null(regional.get_shader_parameter("profile_tex"), "update never writes it")
	for seg: Dictionary in slab._segments:
		var mat: ShaderMaterial = seg["mesh"].material_override
		assert_ne(mat, regional)
		assert_not_null(mat.get_shader_parameter("profile_tex"), "segments keep their own")
	slab.set_extension_material(null)
	for ext: Dictionary in slab._extensions:
		assert_same(ext["mesh"].material_override, ext["placeholder"], "null restores it")


func test_no_fill_lights_the_face_turned_from_the_sun() -> void:
	# Replaces #646's criterion 14, which asserted a fill of 0.35. Edwin withdrew
	# the fill on 2026-11-25 ("it's ok to make the left side darker to fit the
	# shadows"; #680, ADR-022 decision 1, Lighting): the faces take the scene's
	# light alone, so nothing on the slab emits.
	var fields := ScenarioCatalog.default_fields()
	var slab := _slab(fields)
	slab.update(_patches(fields))
	# Segments draw with the face shader, extensions with the regional one.
	var faces: Array[Dictionary] = slab._segments + slab._extensions
	for face: Dictionary in faces:
		var mesh: MeshInstance3D = face["mesh"]
		var shader: Shader = (mesh.material_override as ShaderMaterial).shader
		var names := shader.get_shader_uniform_list().map(
			func(u: Dictionary) -> String: return u["name"]
		)
		assert_false("face_fill" in names, "%s takes no fill" % shader.resource_path)
		assert_false(shader.code.contains("EMISSION"), "%s emits nothing" % shader.resource_path)
		assert_null(mesh.get_instance_shader_parameter("face_fill"), "no per-quad fill")
	var placeholder: Shader = (slab._extensions[0]["placeholder"] as ShaderMaterial).shader
	assert_false(placeholder.code.contains("EMISSION"), "nor the placeholder")
	for side: Dictionary in slab._sides:
		var plain: StandardMaterial3D = side["mesh"].material_override
		assert_false(plain.emission_enabled, "a closed side does not glow")


func test_faces_take_their_soils_cited_hue() -> void:
	# #680: per depth, the gain that gives the cross texture the cited hue of
	# its patch's soil; Kenya's loam takes the KE 1 Nitisol hue by climate.
	var cases := {
		0: ["sandy_temperate", "loam_temperate", "clay_temperate"],
		SAHEL: ["sandy_subsaharan"],
		1: ["loam_temperate@kenya_highlands"],
	}
	for id: int in cases:
		var fields := ScenarioCatalog.fields_for(id)
		var slab := _slab(fields)
		var patches := _patches(fields)
		slab.update(patches)
		for seg: Dictionary in slab._segments:
			var why := "%s, patch %d" % [ScenarioCatalog.label_for(id), seg["patch_idx"]]
			assert_eq(seg["soil_key"], cases[id][seg["patch_idx"]], why)
			var soil: Dictionary = patches[seg["field_id"]][seg["patch_idx"]]["soil_state"]
			var want := SoilFaceColour.hue_samples(soil, seg["soil_key"], slab._section_cm)
			var mat: ShaderMaterial = seg["mesh"].material_override
			var got: Image = (mat.get_shader_parameter("hue_tex") as Texture2D).get_image()
			assert_eq(got.get_height(), want.size(), "one gain per profile sample")
			for p: int in [0, want.size() / 2, want.size() - 1]:
				var g := got.get_pixel(0, p)
				var w: Color = want[p]
				assert_almost_eq(
					Vector3(g.r, g.g, g.b), Vector3(w.r, w.g, w.b), Vector3.ONE * 1e-4, why
				)


## Enter the farm view with no game, so nothing loads or steps on its own.
func _view() -> Node3D:
	var api := FarmViewTest.ApiStub.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	return view


## Where `point` projects at 1280x720 through a copy of `cam`.
func _project(cam: Camera3D, point: Vector3) -> Vector2:
	var vp := SubViewport.new()
	vp.size = Vector2i(1280, 720)
	add_child_autofree(vp)
	var probe := Camera3D.new()
	probe.projection = cam.projection
	probe.size = cam.size
	vp.add_child(probe)
	probe.global_transform = cam.global_transform
	return probe.unproject_position(point)


func test_every_step_result_refreshes_the_slab() -> void:
	var view := _view()
	var slab: DioramaSlab = view._slab
	var fields := ScenarioCatalog.default_fields()
	var mat: ShaderMaterial = slab._segments[0]["mesh"].material_override
	view._on_step_complete(true, {"day_number": 1, "weather": {}, "patches": _patches(fields)})
	var first: Texture2D = mat.get_shader_parameter("profile_tex")
	assert_true(slab._segments.all(func(s: Dictionary) -> bool: return s["mesh"].visible))
	view._on_season_complete(
		true, {"day_number": 9, "weather": {}, "patches": _patches(fields, 0.1)}
	)
	var dried: Texture2D = mat.get_shader_parameter("profile_tex")
	assert_ne(dried, first, "Run Season's final result redraws the faces")
	assert_gt(dried.get_image().get_pixel(0, 10).r, first.get_image().get_pixel(0, 10).r, "drier")


func test_camera_frames_the_slab_in_every_scenario() -> void:
	var view := _view()
	assert_eq(view.camera_rig.position.y, -0.5, "the rig is lowered half a world unit")
	assert_eq(view.camera.size, 10.0, "orthographic size unchanged")
	for id in range(ScenarioCatalog.option_count()):
		var fields := ScenarioCatalog.fields_for(id)
		view._apply_layout(fields)
		view._slab.update(_patches(fields))
		var corner: Vector2 = _project(view.camera, view._slab.front_corner())
		assert_lt(corner.y, 625.0, "%s: corner above the BottomBar" % ScenarioCatalog.label_for(id))


func test_a_click_on_the_front_tile_still_selects_it() -> void:
	var view := _view()
	view._slab.update(_patches(ScenarioCatalog.default_fields()))
	await wait_physics_frames(2)
	var front: Vector3 = view._tile_meshes[35].global_position
	for inset: Vector3 in [Vector3.ZERO, Vector3(0.4, 0.0, 0.4)]:
		view._handle_click(view.camera.unproject_position(front + inset))
		assert_eq(view._selected_tile, Vector2i(5, 5), "tile (5, 5), inset %s" % inset)
