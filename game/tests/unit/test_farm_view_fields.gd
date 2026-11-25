extends GutTest
## The farm view with every field on the map (#600, #472 C-b): fields are row
## bands of the 6x6 grid with FarmLayout.FIELD_GAP between them, and day
## results, Plant and Harvest, stress icons, history, the soil cutaway and a
## reconcile all map by (field, patch). Kept apart from test_farm_view.gd, which
## is at gdlint's public-method cap.

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")

var _auto_cutaway: bool


## FarmViewTest's stub, also recording cost previews and report fetches; it
## answers nothing but the layout load, so each test drives its own replies.
class Stub:
	extends FarmViewTest.ApiStub

	func preview_action(
		_id: String, field_id: String, action: String, params: Dictionary, _cb: Callable
	) -> void:
		calls.append(["preview", field_id, action, params])

	func get_report(_id: String, _cb: Callable) -> void:
		calls.append(["get_report"])


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)
	GameState.game_id = ""


## GET /games/{id}'s `fields`: field_1 is the default scenario's three patches
## (sandy, loam, clay) and field_2 one rice patch on clay, #600's [3, 1] layout.
func _fields() -> Dictionary:
	var rice := {
		"soil_profile_key": "clay_temperate",
		"crop_key": "rice",
		"climate_key": "netherlands_temperate",
		"area_fraction": 1.0,
	}
	return {"field_1": ScenarioCatalog.default_patches(), "field_2": [rice]}


## Enter the farm view on game "g", whose GET /games/{id} carries `fields`.
func _enter(fields: Dictionary) -> Node3D:
	GameState.game_id = "g"
	var api := Stub.new()
	api.game_reply = [true, {"game_id": "g", "fields": fields}]
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	return view


## The (field, patch) the [3, 1] layout puts on tile `i`.
func _owner(i: int) -> Array:
	if floori(i / 6.0) < 3:
		return ["field_1", FarmLayout.patch_for_column(i % 6, 3, 6)]
	return ["field_2", 0]


## `key` of all 36 tiles, row-major.
func _grid(view: Node3D, key: String) -> Array:
	return view._tile_data.map(func(t: Dictionary) -> Variant: return t.get(key))


## 18 values for rows 0-2, then 18 for rows 3-5.
func _bands(upper: Variant, lower: Variant) -> Array:
	var out: Array = []
	for i in range(36):
		out.append(upper if i < 18 else lower)
	return out


## Indices of the tiles carrying a stress icon, ascending.
func _icon_tiles(view: Node3D) -> Array:
	var tiles: Array = view._stress_icons._icons.keys().map(func(k: String) -> int: return int(k))
	tiles.sort()
	return tiles


## A growing patch of `crop` with the given surface moisture and soil carbon.
func _day(crop: String, theta: float, som: float) -> Dictionary:
	return {
		"crop_key": crop,
		"crop_stage": "vegetative",
		"lai": 10.0 * theta,
		"soil_theta_surface": theta,
		"som_total_c_g_m2": som,
	}


func test_two_fields_render_as_row_bands_with_a_gap() -> void:
	var view := _enter(_fields())
	assert_false(view.next_day_btn.disabled, "actions enabled once laid out")
	assert_eq(
		view._layout.map(func(f: Dictionary) -> String: return f["field_id"]),
		["field_1", "field_2"]
	)
	var total_z := 0.0
	for i in range(36):
		var tile: Dictionary = view._tile_data[i]
		assert_eq([tile["field_id"], tile["patch_idx"]], _owner(i), "tile %d" % i)
		var mesh: MeshInstance3D = view._tile_meshes[i]
		assert_eq(mesh.position.x, (i % 6) - 2.5, "columns do not move")
		assert_eq(
			(view._crop_sprites[i][0] as Node3D).position, mesh.position, "crops on their tile"
		)
		total_z += mesh.position.z
	assert_almost_eq(total_z / 36.0, 0.0, 1e-6, "the grid stays centred")
	var z: Array = range(6).map(
		func(row: int) -> float: return view._tile_meshes[row * 6].position.z
	)
	for row in range(1, 6):
		var step: float = FarmView.TILE_SIZE + (FarmLayout.FIELD_GAP if row == 3 else 0.0)
		assert_almost_eq(z[row] - z[row - 1], step, 1e-6, "row %d after row %d" % [row, row - 1])
	# field_2's clay on rows 3-5, under field_1's sandy column 0.
	assert_eq(
		[view._tile_data[0]["soil_type"], view._tile_data[18]["soil_type"]], ["sandy", "clay"]
	)
	var tex: Texture2D = view._tile_materials[18].get_shader_parameter("albedo_texture")
	assert_eq(tex.resource_path, FarmLayout.SOIL_TEXTURES["clay"]["albedo"])


func test_one_field_leaves_every_tile_where_it_was() -> void:
	var view := _enter({"field_1": ScenarioCatalog.default_patches()})
	for i in range(36):
		var at := Vector3((i % 6) - 2.5, 0.0, floori(i / 6.0) - 2.5)
		assert_eq((view._tile_meshes[i] as MeshInstance3D).position, at, "tile %d" % i)
		assert_eq((view._crop_sprites[i][0] as Node3D).position, at, "crops %d" % i)


func test_a_layout_that_does_not_fit_holds_the_bar_and_hides_no_field() -> void:
	var patch := {"soil_profile_key": "sandy_subsaharan", "crop_key": "maize"}
	var seven_fields := {}
	for i in range(7):
		seven_fields["f%d" % i] = [patch]
	var wide := {"wide": [patch, patch, patch, patch, patch, patch, patch]}
	var cases: Array = [
		[seven_fields, "7 fields, but the map has 6 rows"],
		[wide, "wide has 7 patches; a field takes 1 to 6"],
	]
	for case: Array in cases:
		var view := _enter(case[0])
		var why: String = case[1]
		assert_eq(view.status_label.text, "Error: game g does not fit the map: %s" % why)
		for btn: String in FarmViewTest._BAR:
			assert_true(view.get(btn).disabled, "%s held: %s" % [btn, why])
		# Nothing of the game is laid out, so no field is shown cut short.
		assert_eq(view._layout, ScenarioCatalog.default_fields(), "the placeholder stays")
		var laid_out: Array = _grid(view, "field_id").filter(
			func(f: String) -> bool: return f != "field_1"
		)
		assert_eq(laid_out, [], "no tile carries one of the game's fields: %s" % why)
		var api: Stub = view._api_client
		assert_eq(api.calls, [["get_game", "g"]], "no retry: the layout itself is the problem")


func test_each_tile_shows_its_own_field_and_patch_after_a_step() -> void:
	# AC 4 and the #563 review: after a step's `patches` are applied, every
	# tile's data and shaded soil follow its own (field, patch). Two steps, so
	# the second payload replaces the first rather than landing once.
	var view := _enter(_fields())
	for step: int in [1, 2]:
		var wet: float = 0.02 * step
		var patches := {
			"field_2": [_day("rice", 0.32 + wet, 4000.0 + step)],
			"field_1":
			[
				_day("maize", 0.08 + wet, 1000.0 + step),
				_day("maize", 0.16 + wet, 2000.0 + step),
				_day("maize", 0.24 + wet, 3000.0 + step),
			],
		}
		view._apply_patch_data(patches)
		assert_eq(_grid(view, "crop_key"), _bands("maize", "rice"), "step %d" % step)
		for i in range(36):
			var key: Array = _owner(i)
			var want: Dictionary = patches[key[0]][key[1]]
			assert_eq(view._tile_data[i]["lai"], want["lai"], "tile %d, step %d" % [i, step])
			var mat: ShaderMaterial = view._tile_materials[i]
			var moisture: float = want["soil_theta_surface"] / FarmView.THETA_SATURATED
			assert_almost_eq(mat.get_shader_parameter("moisture_frac"), moisture, 1e-6)
			var som: float = want["som_total_c_g_m2"] / FarmView.SOM_MAX_C_G_M2
			assert_almost_eq(mat.get_shader_parameter("som_frac"), som, 1e-6)
	await wait_process_frames(1)  # replaced plants are queue_free'd
	for i: int in [0, 17, 18, 35]:
		assert_gt(view._crop_sprites[i][0].get_child_count(), 0, "tile %d draws its crop" % i)


func test_plant_and_harvest_name_the_selected_tiles_field_and_patch() -> void:
	var view := _enter(_fields())
	var api: Stub = view._api_client
	var sorghum: int = FarmView.AVAILABLE_CROPS.find("sorghum")
	for case: Array in [[Vector2i(0, 4), "field_2", 0], [Vector2i(5, 0), "field_1", 2]]:
		var tile: Vector2i = case[0]
		var field: String = case[1]
		var patch: int = case[2]
		view._tile_data[tile.y * 6 + tile.x].merge({"crop_key": "maize", "crop_stage": 2}, true)
		view._select_tile(tile.x, tile.y)
		view._on_plant_pressed()
		view._crop_popup.hide()
		var preview := ["preview", field, "plant", {"crop_key": "grape", "patch_idx": patch}]
		assert_eq(api.calls[-1], preview, "the seed cost previewed from %s" % tile)
		view._on_crop_selected(sorghum)
		var plant := ["action", field, "plant", {"crop_key": "sorghum", "patch_idx": patch}]
		assert_eq(api.calls[-1], plant, "plant from %s" % tile)
		view._on_harvest_pressed()
		assert_eq(api.calls[-1], ["action", field, "harvest", {"patch_idx": patch}], "harvest")


func test_plant_and_harvest_replies_change_only_their_fields_rows() -> void:
	var view := _enter(_fields())
	var maize := {"crop_key": "maize", "crop_stage": "vegetative", "lai": 2.0}
	var rice := {"crop_key": "rice", "crop_stage": "vegetative", "lai": 1.0}
	view._apply_patch_data({"field_1": [maize, maize, maize], "field_2": [rice]})
	var reply := {"cost_credits": 40, "balance_credits": 900}
	view._on_plant_complete(true, reply, "sorghum", "field_2", 0)
	assert_eq(_grid(view, "crop_key"), _bands("maize", "sorghum"))
	assert_eq(_grid(view, "crop_stage"), _bands(2, 1))
	assert_eq(_grid(view, "lai"), _bands(2.0, 0.0))
	view._on_harvest_complete(true, reply, "sorghum", "field_2", 0)
	assert_eq(_grid(view, "crop_key"), _bands("maize", ""))
	assert_eq(_grid(view, "crop_stage"), _bands(2, 0))
	assert_eq(_grid(view, "lai"), _bands(2.0, 0.0), "field_1 keeps growing")


func test_stress_icons_go_to_the_rows_of_the_field_they_hit() -> void:
	var view := _enter(_fields())
	var frost := {"event_type": "FrostDamageApplied", "module": "t", "data": {"severity": 0.5}}
	var calm := {"events": []}
	var hit := {"events": [frost]}
	view._apply_patch_data({"field_1": [calm, calm, calm], "field_2": [hit]})
	assert_eq(_icon_tiles(view), range(18, 36), "field_2's patch 0: rows 3-5 only")
	# The next day the frost hits field_1's patch 0 instead: rows 0-2, columns 0-1.
	view._apply_patch_data({"field_1": [hit, calm, calm], "field_2": [calm]})
	assert_eq(_icon_tiles(view), [0, 1, 6, 7, 12, 13], "field_1's patch 0 only")


func test_snapshots_file_each_field_and_patch_apart() -> void:
	var view := _enter(_fields())
	var snaps: Array = [
		{"day_number": 5, "field_id": "field_1", "patch_idx": 0, "lai": 1.0},
		{"day_number": 5, "field_id": "field_2", "patch_idx": 0, "lai": 2.0},
		{"day_number": 5, "field_id": "field_3", "patch_idx": 0, "lai": 3.0},  # no such field
		{"day_number": 5, "field_id": "field_2", "patch_idx": 1, "lai": 4.0},  # no such patch
	]
	view._apply_day_result({"day_number": 5, "daily_snapshots": snaps, "patches": {}})
	var history: Dictionary = view._daily_history
	assert_eq(history.keys(), ["field_1/0", "field_2/0"], "one history each, the rest skipped")
	var lai := func(key: String) -> Array:
		return history[key].map(func(r: Dictionary) -> float: return r["lai"])
	assert_eq([lai.call("field_1/0"), lai.call("field_2/0")], [[1.0], [2.0]], "one record each")
	# Tile (0, 4) reads field_2's history, (0, 0) field_1's.
	assert_eq(FarmLayout.tile_key(view._tile_data[24]), "field_2/0")
	assert_eq(FarmLayout.tile_key(view._tile_data[0]), "field_1/0")


func test_the_cutaway_column_reads_its_tiles_own_field_and_patch() -> void:
	var view := _enter(_fields())
	var soil := func(no3: float) -> Dictionary:
		return {"soil_state": {"n_no3": [no3]}, "events": []}
	# field_2 first and field_1 last, so a loop over fields would end on field_1.
	var patches := {
		"field_2": [soil.call(2.0)],
		"field_1": [soil.call(10.0), soil.call(11.0), soil.call(12.0)],
	}
	var column := func(tile: Vector2i) -> Dictionary:
		return view._cutaway._get_soil_column(
			tile, patches, true, view._tile_data, view._tile_meshes, FarmView.GRID_COLS
		)
	var lower: Dictionary = column.call(Vector2i(0, 4))
	assert_eq(lower["soil_state"], {"n_no3": [2.0]}, "tile (0, 4) is field_2's patch 0")
	assert_eq(lower["pos"], view._tile_meshes[24].position)
	assert_eq(column.call(Vector2i(5, 0))["soil_state"], {"n_no3": [12.0]}, "field_1's patch 2")
	# A patch the payload lacks has no column, never another field's or index's.
	patches["field_2"] = []
	assert_eq(column.call(Vector2i(0, 4)), {}, "no fallback")


func test_a_reconcile_changing_field_2_updates_its_rows_only() -> void:
	# #571 review: GET /games/{id}'s crops are the truth for every field.
	var view := _enter(_fields())
	var maize := {"crop_key": "maize", "crop_stage": "vegetative", "lai": 2.0}
	var rice := {"crop_key": "rice", "crop_stage": "vegetative", "lai": 1.0}
	view._apply_patch_data({"field_1": [maize, maize, maize], "field_2": [rice]})
	var server: Array = [{"crop_key": "maize"}, {"crop_key": "maize"}, {"crop_key": "maize"}]
	for crop: String in ["sorghum", ""]:
		var fields := {"field_1": server, "field_2": [{"crop_key": crop}]}
		var game := {"balance_credits": 900, "fields": fields}
		view._on_reconciled(true, game, "Plant failed", view._releases)
		assert_eq(_grid(view, "crop_key"), _bands("maize", crop), "field_2 now %s" % crop)
		assert_eq(_grid(view, "lai"), _bands(2.0, 0.0), "field_1 keeps its growth")
		var reread := "Plant failed; credits and crops re-read from the server"
		assert_eq(view.status_label.text, reread)


## A step of `n` days in which only field_1's patch 0 has heat, on day `heat_day`.
func _heat_step(n: int, heat_day: int, first: int = 1) -> Dictionary:
	var snaps: Array = []
	for d in range(first, first + n):
		for field: String in ["field_1", "field_2"]:
			var events: Array = []
			if field == "field_1" and d == heat_day:
				events.append(
					{
						"event_type": "HeatDamageApplied",
						"data": {"grain_reduction_factor": 0.5, "threshold_c": 35.0}
					}
				)
			(
				snaps
				. append(
					{
						"day_number": d,
						"field_id": field,
						"patch_idx": 0,
						"crop_stage": "vegetative",
						"dev_stage": 0.1 + 0.01 * d,
						"root_depth_cm": 10.0 + d,
						"events": events,
					}
				)
			)
	var maize := {"crop_key": "maize", "crop_stage": "vegetative", "events": []}
	var rice := {"crop_key": "rice", "crop_stage": "vegetative", "events": []}
	var patches := {
		"field_1": [maize.duplicate(true), maize.duplicate(true), maize.duplicate(true)]
	}
	patches["field_2"] = [rice.duplicate(true)]
	patches["field_1"][0]["root_depth_cm"] = 10.0 + first + n - 1
	patches["field_2"][0]["root_depth_cm"] = 30.0
	return {"day_number": first + n - 1, "daily_snapshots": snaps, "patches": patches}


func _card_texts(view: Node3D) -> Array:
	var out: Array = []
	for lbl: Label in view._quick_status.find_children("*", "Label", true, false):
		out.append(lbl.text)
	return out


func test_damage_latches_over_a_step_for_its_own_field_only() -> void:
	var view := _enter(_fields())
	view._apply_day_result(_heat_step(7, 3))
	for i in range(36):
		var field: String = _owner(i)[0]
		var patch: int = _owner(i)[1]
		var hot: bool = field == "field_1" and patch == 0
		assert_eq(view._tile_data[i]["heat_damage"], 0.5 if hot else 0.0, "tile %d" % i)
		assert_eq(view._tile_data[i].get("heat_days", 0), 1 if hot else 0, "tile %d" % i)
	assert_eq(_icon_tiles(view), [0, 1, 6, 7, 12, 13], "the icon latches though day 7 was calm")
	var keys: Array = view._stress_icons._icons["0"].get_meta("stress_keys")
	assert_has(keys, "HeatDamageApplied")


func test_card_follows_the_selected_tiles_field_and_patch() -> void:
	var view := _enter(_fields())
	view._apply_day_result(_heat_step(7, 3))
	view._select_tile(0, 0)
	var f1 := _card_texts(view)
	assert_has(f1, "Heat: 1 day above 35 °C during flowering or grain fill")
	assert_has(f1, "Roots 17 cm")
	view._select_tile(0, 4)
	var f2 := _card_texts(view)
	assert_has(f2, "Roots 30 cm", "field 2's patch, not field 1's")
	assert_eq(f2.filter(func(t: String) -> bool: return t.begins_with("Heat")), [])
	assert_has(f2, "Vegetative")


func test_heat_counts_carry_across_steps_and_reset_on_replant_and_harvest() -> void:
	var view := _enter(_fields())
	view._apply_day_result(_heat_step(7, 3))
	view._apply_day_result(_heat_step(7, 9, 8))
	assert_eq(view._tile_data[0]["heat_days"], 2)
	# Season two: the rollover replants, DVS falls, and the count starts again.
	var rollover := _heat_step(7, 16, 15)
	for snap: Dictionary in rollover["daily_snapshots"]:
		snap["dev_stage"] = 0.01 * (snap["day_number"] - 14)
	view._apply_day_result(rollover)
	assert_eq(view._tile_data[0]["heat_days"], 1, "season two's own day")
	# Plant resets it, and Harvest clears the icons of its patch only.
	view._on_plant_complete(true, {}, "sorghum", "field_1", 0)
	assert_eq(view._tile_data[0]["heat_days"], 0)
	view._apply_day_result(_heat_step(3, 17, 16))
	view._apply_day_result(_heat_step(3, 17, 19))
	view._tile_data[24]["heat_damage"] = 0.0
	var field_2_icons: Array = _icon_tiles(view).filter(func(i: int) -> bool: return i >= 18)
	view._on_harvest_complete(true, {}, "maize", "field_1", 0)
	assert_eq(_icon_tiles(view).filter(func(i: int) -> bool: return i < 18 and i % 6 < 2), [])
	assert_eq(view._tile_data[0]["heat_days"], 0)
	assert_eq(_icon_tiles(view).filter(func(i: int) -> bool: return i >= 18), field_2_icons)
	view._select_tile(0, 0)
	var texts := _card_texts(view)
	assert_has(texts, "—")
	assert_has(texts, "Roots —")


func test_history_panel_clears_the_card() -> void:
	var view := _enter(_fields())
	view._apply_day_result(_heat_step(2, 1))
	view._select_tile(0, 0)
	view._on_quick_status_history()
	await wait_process_frames(2)
	var panel: Control = view._cutaway._tile_info_panel
	assert_false(view._quick_status.get_global_rect().intersects(panel.get_global_rect()))
	assert_eq(panel.position.x, view._quick_status.position.x + QuickStatusCard.WIDTH + 8.0)
