extends GutTest
## Tests for FarmViewDebug — weather/wind visual helpers and the debug demo
## driver extracted from FarmView.

const FarmViewDebugRef = preload("res://scripts/farm_view_debug.gd")
const FogClouds = preload("res://scripts/fog_clouds_3d.gd")


## Records the calls the driver makes so the demo sequence can be asserted.
class StubApi:
	extends Node
	var plant_calls: Array = []
	var step_calls: Array = []
	var step_should_fail: bool = false

	func execute_action(game_id: String, action: String, params: Dictionary, cb: Callable) -> void:
		if action == "plant":
			plant_calls.append({"game_id": game_id, "params": params})
		cb.call(true, {})

	func step_day(game_id: String, days: int, cb: Callable) -> void:
		step_calls.append({"game_id": game_id, "days": days})
		cb.call(not step_should_fail, {"day_number": days})


func test_update_weather_lighting_dims_sun_on_rain() -> void:
	var sun := DirectionalLight3D.new()
	add_child_autofree(sun)
	var world_env := WorldEnvironment.new()
	world_env.environment = Environment.new()
	add_child_autofree(world_env)
	var fog: GPUParticles3D = FogClouds.new()
	add_child_autofree(fog)

	FarmViewDebugRef.update_weather_lighting({"rain_mm": 0.0}, sun, world_env, fog)
	var sunny_energy: float = sun.light_energy
	FarmViewDebugRef.update_weather_lighting({"rain_mm": 10.0}, sun, world_env, fog)
	var rainy_energy: float = sun.light_energy
	assert_lt(rainy_energy, sunny_energy, "overcast should dim the sun")


func test_update_weather_lighting_handles_missing_environment() -> void:
	var sun := DirectionalLight3D.new()
	add_child_autofree(sun)
	var world_env := WorldEnvironment.new()  # no Environment resource assigned
	add_child_autofree(world_env)
	var fog: GPUParticles3D = FogClouds.new()
	add_child_autofree(fog)
	# Should set the sun and return early without touching ambient/fog.
	FarmViewDebugRef.update_weather_lighting({"rain_mm": 3.0}, sun, world_env, fog)
	assert_lt(sun.light_energy, 1.15, "sun still adjusted even without an Environment")


func test_apply_wind_pushes_params_onto_crop_materials() -> void:
	var container := Node3D.new()
	add_child_autofree(container)
	var mesh := MeshInstance3D.new()
	var mat := ShaderMaterial.new()
	mesh.material_override = mat
	container.add_child(mesh)
	# One tile with a crop container, one empty tile (must be skipped safely).
	FarmViewDebugRef.apply_wind_to_all_crops([[container], []], 0.7, Vector2(1, 0))
	assert_almost_eq(mat.get_shader_parameter("wind_strength"), 0.7, 0.001)


func test_apply_wind_empty_list_is_noop() -> void:
	# No crops at all — must not raise.
	FarmViewDebugRef.apply_wind_to_all_crops([], 0.5, Vector2(0, 1))
	assert_true(true, "empty crop list handled")


func test_inject_debug_stress_events_appends_to_each_patch() -> void:
	var patches: Dictionary = {
		"field_a": [{"events": []}, {"events": [{"event_type": "Existing"}]}],
	}
	FarmViewDebugRef.inject_debug_stress_events(patches)
	var n_fake: int = FarmViewDebugRef.FAKE_STRESS_EVENTS.size()
	assert_eq(patches["field_a"][0]["events"].size(), n_fake, "empty patch gets fake events")
	assert_eq(patches["field_a"][1]["events"].size(), n_fake + 1, "existing events are preserved")


func test_start_runs_plant_then_step_then_show_sequence() -> void:
	var api := StubApi.new()
	add_child_autofree(api)
	var debug := FarmViewDebugRef.new()
	var applied: Array = []
	var selected: Array = []
	var shown: Array = []
	debug.start(
		{
			"api": api,
			"game_id_fn": func() -> String: return "g1",
			"ensure_game_fn": func(cb: Callable) -> void: cb.call(),
			"apply_step_fn": func(data: Dictionary) -> void: applied.append(data),
			"select_tile_fn": func(col: int, row: int) -> void: selected.append(Vector2i(col, row)),
			"show_cutaway_fn": func() -> void: shown.append(true),
		}
	)
	# StubApi resolves callbacks synchronously, so the demo runs to completion.
	assert_eq(api.plant_calls.size(), 3, "auto-plants three demo crops")
	assert_eq(api.plant_calls[0]["params"]["crop_key"], "maize")
	assert_eq(api.step_calls.size(), 1, "fast-forwards once")
	assert_eq(api.step_calls[0]["days"], 21, "steps 21 days")
	assert_eq(applied.size(), 1, "applies the stepped result")
	assert_eq(selected[0], Vector2i(1, 3), "selects the demo tile")
	assert_eq(shown.size(), 1, "opens the soil cutaway")


func test_start_stops_on_step_failure() -> void:
	var debug := FarmViewDebugRef.new()
	var api := StubApi.new()
	api.step_should_fail = true
	add_child_autofree(api)
	var shown: Array = []
	debug.start(
		{
			"api": api,
			"game_id_fn": func() -> String: return "g1",
			"ensure_game_fn": func(cb: Callable) -> void: cb.call(),
			"apply_step_fn": func(_d: Dictionary) -> void: pass,
			"select_tile_fn": func(_c: int, _r: int) -> void: pass,
			"show_cutaway_fn": func() -> void: shown.append(true),
		}
	)
	# Planting still happens, but a failed step must not open the cutaway.
	assert_eq(api.plant_calls.size(), 3, "crops still planted before the step")
	assert_eq(shown.size(), 0, "cutaway not opened when the step fails")
