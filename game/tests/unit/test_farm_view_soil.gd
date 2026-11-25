extends GutTest
## View Soil after the pit (#647, ADR-022): it opens the Soil Analysis panel for
## the selected tile and leaves the 3D farm alone. The panel follows the
## selection, refreshes in place on each day tick, fits above the bottom bar,
## and closes on View Soil, Esc or a deselect.

const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")
## Layer thicknesses (cm) of the default farm's sandy, loam and clay patches,
## from data/soils/presets.yaml.
const LAYERS := [[25.0, 35.0, 40.0], [25.0, 35.0, 40.0], [30.0, 35.0, 40.0]]

var _auto_soil_view: bool
var _mass_unit: Variant


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_soil_view = ProjectSettings.get_setting("agrogame/debug/auto_soil_view", false)
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", false)
	_mass_unit = ProjectSettings.get_setting("agrogame/display/mass_unit")
	ProjectSettings.set_setting("agrogame/display/mass_unit", UiTheme.MASS_UNIT_GM2)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", _auto_soil_view)
	ProjectSettings.set_setting("agrogame/display/mass_unit", _mass_unit)
	GameState.game_id = ""


## The default farm (sandy, loam, clay) on game "g", after one /step whose
## layers all hold `no3`, with tile (1, 3) selected.
func _enter(no3: float = 5.0) -> Node3D:
	GameState.game_id = "g"
	var api := FarmViewTest.ApiStub.new()
	var fields := {"field_1": ScenarioCatalog.default_patches()}
	api.game_reply = [true, {"game_id": "g", "fields": fields}]
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._on_step_complete(true, _step(no3))
	view._select_tile(1, 3)
	return view


## A /step reply: three growing maize patches, each layer holding `no3` and
## the profile keys the slab draws (#646).
func _step(no3: float) -> Dictionary:
	var patches: Array = []
	for thickness: Array in LAYERS:
		var per_layer := {
			"n_no3": no3,
			"texture": "loam",
			"soc_pct": 1.0,
			"water_theta": 0.2,
			"field_capacity": 0.25,
			"wilting_point": 0.12,
		}
		var soil := {"layer_thickness_cm": thickness}
		for key: String in per_layer:
			soil[key] = thickness.map(func(_t: float) -> Variant: return per_layer[key])
		patches.append(
			{"crop_key": "maize", "crop_stage": "vegetative", "lai": 1.0, "soil_state": soil}
		)
	return {"day_number": 2, "date": "2026-05-02", "weather": {}, "patches": {"field_1": patches}}


func _panel(view: Node3D) -> PanelContainer:
	return view._soil_panel._nutrient_panel


func _headers(view: Node3D) -> Array:
	return _panel(view)._layer_headers.map(func(b: Button) -> String: return b.text)


## Per layer: [open, details shown].
func _states(view: Node3D) -> Array:
	var panel := _panel(view)
	var out: Array = []
	for i in range(panel._layer_bodies.size()):
		out.append([panel._layer_bodies[i].visible, panel._layer_details[i].visible])
	return out


## Layer 0's NO₃ value as shown.
func _no3(view: Node3D) -> String:
	return (_panel(view)._layer_bodies[0].get_child(0).get_child(3) as Label).text


func test_view_soil_opens_the_panel_and_moves_nothing_in_the_world() -> void:
	var view := _enter()
	var camera: Transform3D = view.camera.global_transform
	var nodes_3d: int = view.find_children("*", "Node3D", true, false).size()
	view.soil_view_btn.pressed.emit()
	for i in range(36):
		assert_true(view._tile_meshes[i].visible, "tile %d shown" % i)
		assert_true((view._crop_sprites[i][0] as Node3D).visible, "crops %d shown" % i)
	assert_eq(view.camera.global_transform, camera, "the camera stays put")
	assert_eq(view.find_children("*", "Node3D", true, false).size(), nodes_3d, "no 3D node added")
	var panel: Control = view.get_node("UILayer/SoilAnalysisPanel")
	assert_same(panel, _panel(view))
	assert_true(panel.visible)
	assert_eq(_headers(view), ["▾ 0–25cm", "▸ 25–60cm", "▸ 60–100cm"], "the sandy patch")


func test_another_tile_shows_its_own_patch_at_its_own_depths() -> void:
	var view := _enter()
	view.soil_view_btn.pressed.emit()
	view._select_tile(4, 1)
	assert_true(view._soil_panel.is_open(), "the panel follows the selection")
	assert_eq(_headers(view), ["▾ 0–30cm", "▸ 30–65cm", "▸ 65–105cm"], "the clay patch")


func test_the_panel_stays_above_the_bottom_bar_and_scrolls_when_expanded() -> void:
	var view := _enter()
	view.soil_view_btn.pressed.emit()
	var panel := _panel(view)
	var bar: Control = view.get_node("UILayer/BottomBar")
	assert_eq(view.get_viewport().get_visible_rect().size, Vector2(1280, 720))
	var steps := {
		"default": func() -> void: pass,
		"layer 1 open": func() -> void: panel._on_layer_header(1),
		"layers 0 to 2 open": func() -> void: panel._on_layer_header(2),
		"Expand All": func() -> void: panel._on_expand_all(),
		"a day tick with Expand All": func() -> void: view._on_step_complete(true, _step(6.0)),
	}
	for state: String in steps:
		(steps[state] as Callable).call()
		await wait_process_frames(2)
		var bottom: float = panel.get_global_rect().end.y
		assert_lt(bottom, bar.get_global_rect().position.y, "%s: above the bar" % state)
		assert_almost_eq(panel.get_global_rect().position.y, 16.0, 0.5, "%s: top" % state)
		assert_almost_eq(panel.get_global_rect().end.x, 1264.0, 0.5, "%s: right" % state)
		# A refresh must not leave the frame at its empty minimum (#647).
		assert_eq(panel.size, panel.get_combined_minimum_size(), "%s: hugs its rows" % state)
	assert_lt(panel._scroll.size.y, panel._list.get_combined_minimum_size().y, "the list scrolls")


func test_open_layers_and_expand_all_survive_a_step_and_a_tile_switch() -> void:
	var view := _enter()
	view.soil_view_btn.pressed.emit()
	var panel := _panel(view)
	panel._on_layer_header(2)
	view._on_step_complete(true, _step(7.0))
	assert_same(_panel(view), panel, "refreshed in place")
	assert_eq(_states(view), [[true, false], [false, false], [true, false]])
	assert_eq(_no3(view), "7.0 g/m²", "the new value")
	panel._on_expand_all()
	view._on_step_complete(true, _step(9.0))
	assert_eq(_states(view), [[true, true], [true, true], [true, true]], "Expand All holds")
	assert_eq(_no3(view), "9.0 g/m²")
	view._select_tile(4, 1)
	assert_same(_panel(view), panel)
	assert_eq(_states(view), [[true, true], [true, true], [true, true]], "and on another tile")


func test_view_soil_toggles_and_esc_or_a_deselect_closes_it() -> void:
	var view := _enter()
	view.soil_view_btn.pressed.emit()
	view.soil_view_btn.pressed.emit()
	assert_false(view._soil_panel.is_open(), "a second press closes it")
	view._quick_status.soil_view_requested.emit()
	assert_true(view._soil_panel.is_open(), "the Quick Status card's soil button opens it")
	var esc := InputEventKey.new()
	esc.pressed = true
	esc.keycode = KEY_ESCAPE
	view._unhandled_input(esc)
	assert_false(view._soil_panel.is_open(), "Esc closes it")
	view._select_tile(1, 3)
	view.soil_view_btn.pressed.emit()
	await wait_physics_frames(2)
	view._handle_click(Vector2(2, 2))  # the sky, above the farm
	assert_eq(view._selected_tile, Vector2i(-1, -1))
	assert_false(view._soil_panel.is_open(), "a click on empty ground closes it")
	await wait_process_frames(1)
	assert_null(view.get_node_or_null("UILayer/SoilAnalysisPanel"), "and frees it")


func test_view_soil_explains_why_it_cannot_open() -> void:
	var view := _enter()
	view._deselect()
	view.soil_view_btn.pressed.emit()
	assert_eq(view.status_label.text, "Select a tile first to view soil")
	view._last_step_data = {}
	view._select_tile(1, 3)
	view.soil_view_btn.pressed.emit()
	assert_eq(view.status_label.text, "Step at least 1 day to see soil data")
	assert_false(view._soil_panel.is_open())
