class_name FarmTiles
extends RefCounted
## The farm view's tile grid: building its nodes, and writing a day's patch
## results into its per-tile data. Moved out of farm_view.gd unchanged (#546) to
## keep that file under the gdlint file-length cap (max-file-lines = 1000).
##
## Tiles are index-aligned across the view's arrays as row * cols + col. Both
## helpers are static and touch only what they are handed: the scene-coupled
## refreshes (tile shader, crop visuals, stress icons) stay in the view.

const SOIL_SHADER := "res://shaders/soil_tile.gdshader"

## API crop_stage name to the view's 0-4 crop stage.
const STAGE_MAP := {
	"planted": 1,
	"emerged": 1,
	"vegetative": 2,
	"flowering": 3,
	"grain_fill": 4,
	"maturity": 4,
}


## Build a grid.x by grid.y tile grid: a soil-shaded plane per tile under
## `tile_root`, each with a StaticBody3D carrying tile_col and tile_row metas for
## the click raycast, plus an empty crop container per tile under `crop_root`.
## Returns the per-tile arrays "meshes", "materials", "crop_sprites" and
## "tile_data", in row-major order.
static func build_grid(
	tile_root: Node3D, crop_root: Node3D, grid: Vector2i, tile_size: float
) -> Dictionary:
	var meshes: Array[MeshInstance3D] = []
	var materials: Array[ShaderMaterial] = []
	var crop_sprites: Array[Array] = []
	var tile_data: Array[Dictionary] = []
	var shader: Shader = load(SOIL_SHADER)
	var box := PlaneMesh.new()
	box.size = Vector2(tile_size, tile_size)
	var offset_x: float = (grid.x - 1) * tile_size / 2.0
	var offset_z: float = (grid.y - 1) * tile_size / 2.0
	for row in range(grid.y):
		for col in range(grid.x):
			var mat := ShaderMaterial.new()
			mat.shader = shader
			mat.set_shader_parameter("som_frac", 0.0)
			mat.set_shader_parameter("moisture_frac", 0.0)
			mat.set_shader_parameter("selected", 0.0)
			var mesh_inst := MeshInstance3D.new()
			mesh_inst.mesh = box
			mesh_inst.material_override = mat
			mesh_inst.position = Vector3(
				col * tile_size - offset_x,
				0.0,
				row * tile_size - offset_z,
			)
			# StaticBody3D for raycast hit detection
			var body := StaticBody3D.new()
			var shape := CollisionShape3D.new()
			var box_shape := BoxShape3D.new()
			box_shape.size = Vector3(tile_size, 0.01, tile_size)
			shape.shape = box_shape
			body.add_child(shape)
			body.set_meta("tile_col", col)
			body.set_meta("tile_row", row)
			mesh_inst.add_child(body)
			tile_root.add_child(mesh_inst)
			meshes.append(mesh_inst)
			materials.append(mat)
			# 3D crop container — plants rebuilt per crop type
			var crop_container := Node3D.new()
			crop_container.position = mesh_inst.position
			crop_root.add_child(crop_container)
			crop_sprites.append([crop_container])
			(
				tile_data
				. append(
					{
						"col": col,
						"row": row,
						"crop_key": "",
						"crop_stage": 0,
						"lai": 0.0,
						"water_stress": 1.0,
						"grain_g_m2": 0.0,
						"som_total_c_g_m2": 0.0,
						"theta_surface": 0.0,
					}
				)
			)
	return {
		"meshes": meshes,
		"materials": materials,
		"crop_sprites": crop_sprites,
		"tile_data": tile_data,
	}


## Per-nutrient stress (#262) and transient morphological damage (#259) from one
## patch's events, each the maximum over the events, 0 = none and 1 = severe.
## Keys: n_stress, p_stress, fe_stress, zn_stress, frost_damage, heat_damage.
static func stress_from_events(events: Array) -> Dictionary:
	var n_stress: float = 0.0
	var p_stress: float = 0.0
	var fe_stress: float = 0.0
	var zn_stress: float = 0.0
	var frost_dmg: float = 0.0
	var heat_dmg: float = 0.0
	for evt: Dictionary in events:
		var et: String = evt.get("event_type", "")
		if et == "NutrientStressComputed":
			var d: Dictionary = evt.get("data", {})
			# API: stress=1 healthy, 0=severe. Invert for display.
			var s: float = clampf(1.0 - d.get("stress", 1.0), 0.0, 1.0)
			match d.get("nutrient", ""):
				"N":
					n_stress = maxf(n_stress, s)
				"P":
					p_stress = maxf(p_stress, s)
				"Fe":
					fe_stress = maxf(fe_stress, s)
				"Zn":
					zn_stress = maxf(zn_stress, s)
		elif et == "FrostDamageApplied":
			var fs: float = clampf(float(evt.get("data", {}).get("severity", 0.5)), 0.0, 1.0)
			frost_dmg = maxf(frost_dmg, fs)
		elif et == "HeatDamageApplied":
			var hs: float = clampf(float(evt.get("data", {}).get("severity", 0.5)), 0.0, 1.0)
			heat_dmg = maxf(heat_dmg, hs)
	return {
		"n_stress": n_stress,
		"p_stress": p_stress,
		"fe_stress": fe_stress,
		"zn_stress": zn_stress,
		"frost_damage": frost_dmg,
		"heat_damage": heat_dmg,
	}


## Write one patch of a /step payload into every tile whose patch_idx matches,
## and return those tiles' indices, ascending, for the caller to refresh.
static func write_patch(patch: Dictionary, patch_idx: int, tile_data: Array) -> Array[int]:
	var stage_name: String = patch.get("crop_stage", "")
	var stage: int = STAGE_MAP.get(stage_name, 0)
	var lai: float = patch.get("lai", 0.0)
	var crop_key: String = patch.get("crop_key", "")
	var theta: float = patch.get("soil_theta_surface", 0.0)
	var grain: float = patch.get("grain_g_m2", 0.0)
	var som: float = patch.get("som_total_c_g_m2", 0.0)
	# Continuous development stage (WOFOST DVS); -1 when the API omits
	# it, in which case the visuals fall back to a per-stage nominal value.
	var dev_stage: float = float(patch.get("dev_stage", -1.0))
	var stress := stress_from_events(patch.get("events", []))
	var written: Array[int] = []
	for i in range(tile_data.size()):
		if tile_data[i]["patch_idx"] != patch_idx:
			continue
		var tile: Dictionary = tile_data[i]
		tile["som_total_c_g_m2"] = som
		tile["theta_surface"] = theta
		# Season-peak LAI anchors canopy-loss senescence; it resets
		# when a new crop is sown or the season restarts.
		var prev_crop: String = tile.get("crop_key", "")
		var prev_peak: float = float(tile.get("lai_peak", 0.0))
		var lai_peak: float = lai
		if stage > 1 and crop_key == prev_crop:
			lai_peak = maxf(prev_peak, lai)
		tile["crop_key"] = crop_key
		tile["crop_stage"] = stage
		tile["lai"] = lai
		tile["dev_stage"] = dev_stage
		tile["lai_peak"] = lai_peak
		tile["water_stress"] = patch.get("water_stress", 1.0)
		tile["grain_g_m2"] = grain
		tile["n_stress"] = stress["n_stress"]
		tile["p_stress"] = stress["p_stress"]
		tile["fe_stress"] = stress["fe_stress"]
		tile["zn_stress"] = stress["zn_stress"]
		tile["frost_damage"] = stress["frost_damage"]
		tile["heat_damage"] = stress["heat_damage"]
		written.append(i)
	return written
