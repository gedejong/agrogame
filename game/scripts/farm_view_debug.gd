class_name FarmViewDebug
extends RefCounted
## Debug/demo driver plus shared world-visual helpers extracted from FarmView.
##
## Two cohesive-but-peripheral concerns live here so farm_view.gd stays under the
## gdlint file-length cap (max-file-lines = 1000):
##   * Weather/wind visual helpers — pure functions over the view's scene nodes
##     and crop sprites (no hidden state), called every simulated day.
##   * A debug demo driver — auto-plants crops, fast-forwards the sim, and opens
##     the soil cutaway for screenshots. It drives FarmView through injected
##     callables (start ctx) so it never reaches into private view members.

const CropRenderer3D = preload("res://scripts/crop_renderer_3d.gd")

## The farm view's sky, ambient light, fog and tonemap. The capture scenes
## light their crops with it too, so their frames show what the player sees.
const FARM_ENVIRONMENT: Environment = preload("res://scenes/farm_environment.tres")
## The sun on a clear day, as update_weather_lighting sets it.
const SUN_COLOR_CLEAR := Color(0.95, 0.9, 0.8)
const SUN_ENERGY_CLEAR := 1.15

## Synthetic stress events injected (behind a project setting) so the stress-icon
## overlay can be exercised without waiting for the simulation to produce them.
const FAKE_STRESS_EVENTS: Array = [
	{"event_type": "FrostDamageApplied", "module": "debug", "data": {"severity": 0.5}},
	# The engine's fields exactly (agrogame/soil/canopy/events.py, #569): spring
	# wheat's 1 - 0.6 on a 34 C flowering day, past its 32 C threshold.
	{
		"event_type": "HeatDamageApplied",
		"module": "debug",
		"data": {"grain_reduction_factor": 0.4, "tmax_c": 34.0}
	},
	{"event_type": "WaterloggingDetected", "module": "debug", "data": {"theta": 0.45}},
	{"event_type": "WaterStressComputed", "module": "debug", "data": {"stress": 0.2}},
	{
		"event_type": "NutrientStressComputed",
		"module": "debug",
		"data": {"nutrient": "N", "stress": 0.1}
	},
	{
		"event_type": "NutrientStressComputed",
		"module": "debug",
		"data": {"nutrient": "P", "stress": 0.3}
	},
]

## Callables/handles supplied by FarmView so the driver can act without touching
## private members. Keys: api, game_id_fn, ensure_game_fn, apply_step_fn,
## select_tile_fn, show_cutaway_fn.
var _ctx: Dictionary = {}


static func update_weather_lighting(
	weather: Dictionary, sun: DirectionalLight3D, env: WorldEnvironment, fog_clouds: GPUParticles3D
) -> void:
	## Adjust sun, ambient, and fog based on weather conditions.
	var rain_mm: float = weather.get("rain_mm", 0.0)
	var tmin: float = weather.get("tmin_c", 10.0)
	var tmax: float = weather.get("tmax_c", 20.0)
	var overcast: float = clampf(rain_mm / 10.0, 0.0, 1.0)
	# Wet-bulb depression proxy: large tmax-tmin = dry, small = humid.
	var temp_spread: float = maxf(tmax - tmin, 1.0)
	# Intentionally produces nonzero humidity on dry days with small temp spread
	# (e.g., calm overcast mornings with dew) — this creates subtle ground fog.
	var humidity_proxy: float = clampf((rain_mm / 5.0) + (1.0 - temp_spread / 15.0) * 0.5, 0.0, 1.0)
	# Sun: dim and cool on rainy days
	var overcast_color := Color(0.65, 0.65, 0.7)
	sun.light_color = SUN_COLOR_CLEAR.lerp(overcast_color, overcast)
	sun.light_energy = lerpf(SUN_ENERGY_CLEAR, 0.5, overcast)
	var e := env.environment
	if not e:
		return
	# Ambient: slightly brighter on overcast (diffuse sky), but greyer
	e.ambient_light_energy = lerpf(0.4, 0.5, overcast)
	var amb_sunny := Color(0.4, 0.42, 0.5)
	var amb_overcast := Color(0.3, 0.3, 0.35)
	e.ambient_light_color = amb_sunny.lerp(amb_overcast, overcast)
	# Fog: driven by humidity proxy, not just rain
	e.fog_density = lerpf(0.001, 0.012, humidity_proxy)
	# Animated fog wisps
	fog_clouds.set_fog_intensity(humidity_proxy)


static func add_farm_lighting(parent: Node, sun_rotation_deg: Vector3) -> DirectionalLight3D:
	## Light parent as the farm view is lit on a clear day: its environment
	## and a shadow-casting sun. The sun's angle is the caller's, since each
	## capture camera needs its own.
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = sun_rotation_deg
	sun.light_color = SUN_COLOR_CLEAR
	sun.light_energy = SUN_ENERGY_CLEAR
	sun.shadow_enabled = true
	parent.add_child(sun)
	var world_env := WorldEnvironment.new()
	world_env.environment = FARM_ENVIRONMENT
	parent.add_child(world_env)
	return sun


static func apply_wind_to_all_crops(
	crop_sprites: Array, wind_strength: float, wind_dir: Vector2
) -> void:
	## Push the current wind vector onto every tile's crop container.
	for sprites: Array in crop_sprites:
		if sprites.size() > 0:
			CropRenderer3D.set_wind(sprites[0], wind_strength, wind_dir)


static func inject_debug_stress_events(patches: Dictionary) -> void:
	## Add fake stress events to each patch for visual debugging.
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		for patch: Dictionary in patch_list:
			var events: Array = patch.get("events", [])
			events.append_array(FAKE_STRESS_EVENTS)
			patch["events"] = events


func start(ctx: Dictionary) -> void:
	## Kick off the auto-cutaway demo: ensure a game exists, then plant crops.
	## ctx keys: api, game_id_fn, ensure_game_fn, apply_step_fn, select_tile_fn, field_id_fn,
	## show_cutaway_fn (see _ctx docstring).
	_ctx = ctx
	var ensure_game_fn: Callable = ctx["ensure_game_fn"]
	ensure_game_fn.call(func() -> void: _plant_crops())


func _plant_crops() -> void:
	var crops := [["maize", 0], ["spring_wheat", 1], ["sorghum", 2]]
	_plant_next(crops, 0)


func _plant_next(crops: Array, idx: int) -> void:
	if idx >= crops.size():
		_step_and_show()
		return
	var c: Array = crops[idx]
	var api: Node = _ctx["api"]
	var game_id_fn: Callable = _ctx["game_id_fn"]
	api.execute_action(
		game_id_fn.call(),
		(_ctx["field_id_fn"] as Callable).call(),
		"plant",
		{"crop_key": c[0], "patch_idx": c[1]},
		func(_s: bool, _d: Dictionary) -> void: _plant_next(crops, idx + 1)
	)


func _step_and_show() -> void:
	var api: Node = _ctx["api"]
	var game_id_fn: Callable = _ctx["game_id_fn"]
	var apply_step_fn: Callable = _ctx["apply_step_fn"]
	var select_tile_fn: Callable = _ctx["select_tile_fn"]
	var show_cutaway_fn: Callable = _ctx["show_cutaway_fn"]
	api.step_day(
		game_id_fn.call(),
		21,
		func(success: bool, data: Dictionary) -> void:
			if not success:
				return
			apply_step_fn.call(data)
			select_tile_fn.call(1, 3)
			show_cutaway_fn.call()
	)
