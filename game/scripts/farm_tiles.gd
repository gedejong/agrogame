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

## Display severity of a HeatDamageApplied event (#664). The event reports
## exposure only (tmax_c, threshold_c) and changes no growth, so the tint
## strength is a UI constant, not a science parameter, the same on every heat
## day. 0.5 is the mid-strength value the tint used before the grain cap was
## retired; its strength is a taste call (#641).
const HEAT_PRESENCE_SEVERITY: float = 0.5

## Per-patch reply fields the Quick Status gauges read (#660, docs/api.md).
const GAUGE_FIELDS: Array[String] = [
	"growth_vs_potential", "root_zone_water_fraction", "depletion_fraction_p"
]


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


## Per-nutrient stress (#262, S and Mn #660) and transient morphological damage
## (#259) from one patch's events, each the maximum over the events, 0 = none and
## 1 = severe. Keys: n_stress, p_stress, s_stress, fe_stress, zn_stress,
## mn_stress, frost_damage, heat_damage, and water_ks, today's Ks: the last
## WaterStressComputed stress (1 = none), as the ADR-017 drought alert reads it.
static func stress_from_events(events: Array) -> Dictionary:
	var n_stress: float = 0.0
	var p_stress: float = 0.0
	var s_stress: float = 0.0
	var fe_stress: float = 0.0
	var zn_stress: float = 0.0
	var mn_stress: float = 0.0
	var frost_dmg: float = 0.0
	var heat_dmg: float = 0.0
	var water_ks: float = 1.0
	for evt: Dictionary in events:
		var et: String = evt.get("event_type", "")
		if et == "WaterStressComputed":
			water_ks = clampf(float(evt.get("data", {}).get("stress", 1.0)), 0.0, 1.0)
		elif et == "NutrientStressComputed":
			var d: Dictionary = evt.get("data", {})
			# API: stress=1 healthy, 0=severe. Invert for display.
			var s: float = clampf(1.0 - d.get("stress", 1.0), 0.0, 1.0)
			match d.get("nutrient", ""):
				"N":
					n_stress = maxf(n_stress, s)
				"P":
					p_stress = maxf(p_stress, s)
				"S":
					s_stress = maxf(s_stress, s)
				"Fe":
					fe_stress = maxf(fe_stress, s)
				"Zn":
					zn_stress = maxf(zn_stress, s)
				"Mn":
					mn_stress = maxf(mn_stress, s)
		elif et == "FrostDamageApplied":
			var fs: float = clampf(float(evt.get("data", {}).get("severity", 0.5)), 0.0, 1.0)
			frost_dmg = maxf(frost_dmg, fs)
		elif et == "HeatDamageApplied":
			heat_dmg = maxf(heat_dmg, heat_severity())
	return {
		"n_stress": n_stress,
		"p_stress": p_stress,
		"s_stress": s_stress,
		"fe_stress": fe_stress,
		"zn_stress": zn_stress,
		"mn_stress": mn_stress,
		"frost_damage": frost_dmg,
		"heat_damage": heat_dmg,
		"water_ks": water_ks,
	}


## Severity in [0, 1] of a HeatDamageApplied event: presence-only (#664), the
## constant HEAT_PRESENCE_SEVERITY whatever the event carries.
static func heat_severity() -> float:
	return HEAT_PRESENCE_SEVERITY


## Write `field_id`'s patch `patch_idx` of a /step payload into every tile laid
## out as that (field, patch) (#600), and return those tiles' indices,
## ascending, for the caller to refresh.
static func write_patch(
	patch: Dictionary, field_id: String, patch_idx: int, tile_data: Array
) -> Array[int]:
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
	var root_cm: float = float(patch.get("root_depth_cm", 0.0))
	var stress := stress_from_events(patch.get("events", []))
	var written := FarmLayout.tiles_of(field_id, patch_idx, tile_data)
	for i: int in written:
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
		tile["crop_stage_name"] = stage_name
		tile["root_depth_cm"] = root_cm
		tile["lai"] = lai
		tile["dev_stage"] = dev_stage
		tile["lai_peak"] = lai_peak
		tile["water_stress"] = patch.get("water_stress", 1.0)
		tile["grain_g_m2"] = grain
		for key: String in stress:
			tile[key] = stress[key]
		# The Quick Status gauges (#660); -1 = not in the reply (JSON null).
		for key: String in GAUGE_FIELDS:
			var value: Variant = patch.get(key)
			tile[key] = -1.0 if value == null else float(value)
	return written


## Take each field's crops in a GET /games/{id} payload's `fields` as the truth,
## for a failed action the server may have applied anyway (#564). Each tile is
## matched by its own field_id and patch_idx, for every field in `fields`. A
## tile whose crop differs from its patch's becomes that crop freshly sown, as
## a Plant reply writes it, or bare, as a Harvest reply does, with no growth
## carried over from the crop it replaces. Tiles whose crop already agrees keep
## their growth. Returns the changed tiles' indices, ascending, for the caller
## to refresh.
static func reconcile_crops(fields: Dictionary, tile_data: Array) -> Array[int]:
	var changed: Array[int] = []
	for i in range(tile_data.size()):
		var tile: Dictionary = tile_data[i]
		var patches: Array = fields.get(tile.get("field_id", ""), [])
		var patch_idx: int = tile.get("patch_idx", -1)
		if patch_idx < 0 or patch_idx >= patches.size():
			continue
		var crop_key: String = patches[patch_idx].get("crop_key", "")
		if crop_key == tile["crop_key"]:
			continue
		_start_crop(tile, crop_key)
		changed.append(i)
	return changed


## Bare `field_id`'s patch `patch_idx` after a Harvest reply, so no growth,
## stress icon input or damage tally outlives the crop. Returns its tiles.
static func clear_crop(field_id: String, patch_idx: int, tile_data: Array) -> Array[int]:
	return sow_crop("", field_id, patch_idx, tile_data)


## `crop_key` freshly sown on `field_id`'s patch `patch_idx`, as a Plant reply
## writes it. Returns its tiles' indices, ascending.
static func sow_crop(
	crop_key: String, field_id: String, patch_idx: int, tile_data: Array
) -> Array[int]:
	var tiles := FarmLayout.tiles_of(field_id, patch_idx, tile_data)
	for i: int in tiles:
		_start_crop(tile_data[i], crop_key)
	return tiles


## Fold the earlier days of a multi-day step's damage into each patch's
## `events`, which hold the last day only, so the 3D heat and frost icons and the
## tile's damage severity latch over the whole step (#630). Drought, nutrient and
## the other stresses keep reading the last day. A last-day event is then in the
## list twice, which the maximum and the icon set do not mind.
static func latch_step_damage(snapshots: Array, patches: Dictionary) -> void:
	for snap: Dictionary in snapshots:
		var patch_list: Array = patches.get(snap.get("field_id", ""), [])
		var idx: int = snap.get("patch_idx", -1)
		if idx < 0 or idx >= patch_list.size():
			continue
		var events: Array = patch_list[idx].get("events", [])
		for evt: Dictionary in snap.get("events", []):
			if evt.get("event_type", "") in [CropStatus.HEAT_KEY, CropStatus.FROST_KEY]:
				events.append(evt)
		patch_list[idx]["events"] = events


## One tile's crop as freshly sown (`crop_key`) or bare (""): no growth, stage,
## roots, stress, damage or tally carried over from the crop it replaces.
static func _start_crop(tile: Dictionary, crop_key: String) -> void:
	tile["crop_key"] = crop_key
	tile["crop_stage"] = 0 if crop_key.is_empty() else 1
	tile["crop_stage_name"] = ""
	tile["root_depth_cm"] = 0.0
	tile["lai"] = 0.0
	tile["lai_peak"] = 0.0
	tile["dev_stage"] = -1.0  # no DVS yet: the visuals take the stage's nominal one
	tile["grain_g_m2"] = 0.0
	tile.merge(stress_from_events([]), true)
	tile["growth_vs_potential"] = -1.0
	tile["depletion_fraction_p"] = -1.0
	CropStatus.reset_tally(tile)
