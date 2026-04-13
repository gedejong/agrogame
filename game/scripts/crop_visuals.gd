class_name CropVisuals
extends RefCounted
## 3D crop rendering: growth/senescence calculation, plant instancing,
## and MultiMesh baking for high-density crops.

## Maximum LAI for normalizing growth. TODO: source from crop presets.
const MAX_LAI := 6.0

const MaizeRenderer3D = preload("res://scripts/maize_renderer_3d.gd")
const WheatRenderer3D = preload("res://scripts/wheat_renderer_3d.gd")
const SorghumRenderer3D = preload("res://scripts/sorghum_renderer_3d.gd")
const RiceRenderer3D = preload("res://scripts/rice_renderer_3d.gd")
const GrapeRenderer3D = preload("res://scripts/grape_renderer_3d.gd")
const CropRenderer3D = preload("res://scripts/crop_renderer_3d.gd")


static func update_crop(
	tile_data: Dictionary,
	crop_sprites: Array,
	crop_grid: Dictionary,
	tile_size: float,
	meters_per_tile: float,
) -> void:
	"""Rebuild 3D crop geometry for a single tile."""
	var crop_key: String = tile_data.get("crop_key", "")
	var stage: int = tile_data.get("crop_stage", 0)
	var lai: float = tile_data.get("lai", 0.0)
	var grain: float = tile_data.get("grain_g_m2", 0.0)
	var plants: Array = crop_sprites
	var lai_frac: float = clampf(lai / MAX_LAI, 0.0, 1.0)
	var grain_frac: float = clampf(grain / 800.0, 0.0, 1.0)
	var growth: float = _calc_growth(stage, lai_frac, grain_frac)
	var senescence: float = _calc_senescence(stage, lai, grain_frac)
	var stresses: Dictionary = StressUtils.parse_stress_data(tile_data)
	var container: Node3D = plants[0]
	for child in container.get_children():
		child.queue_free()
	if stage == 0 or crop_key.is_empty():
		return
	var grid: Vector2i = crop_grid.get(crop_key, Vector2i(4, 4))
	var total_plants: int = grid.x * grid.y
	var col: int = tile_data["col"]
	var row: int = tile_data["row"]
	var s: float = 1.0 / meters_per_tile
	# Morphological stress effects (#259):
	#   Zn deficiency → uniform stunting (smaller plants)
	#   Senescence ≥ 0.85 → vertical collapse (dead plants fall)
	var stunt: float = StressUtils.calc_stunt_factor(stresses)
	var collapse_y: float = StressUtils.calc_collapse_factor(senescence)
	if total_plants > 50:
		_build_baked_plants(
			container,
			crop_key,
			grid,
			col,
			row,
			s,
			growth,
			senescence,
			stresses,
			grain_frac,
			tile_size,
			stunt,
			collapse_y,
		)
	else:
		_build_individual_plants(
			container,
			crop_key,
			grid,
			col,
			row,
			s,
			growth,
			senescence,
			stresses,
			grain_frac,
			tile_size,
			stunt,
			collapse_y,
		)


static func _calc_growth(stage: int, lai_frac: float, grain_frac: float) -> float:
	# Height ∝ sqrt(LAI): leaf area scales with height² (more + bigger leaves),
	# so height = sqrt(lai_frac). This prevents doubling LAI from doubling
	# visual height — instead it gives ~40% height increase (physically correct).
	if stage == 0:
		return 0.0
	var base: float = sqrt(clampf(lai_frac, 0.0, 1.0))
	# Floor: emerged plants have at least 5% even at LAI~0
	var floor_val: float = 0.05
	# Grain fill adds a small top-end boost (stem extension)
	var grain_boost: float = grain_frac * 0.1 if stage >= 3 else 0.0
	return clampf(maxf(base, floor_val) + grain_boost, 0.0, 1.0)


static func _calc_senescence(stage: int, lai: float, grain_frac: float) -> float:
	# Senescence: gradual onset from flowering onward.
	# During vegetative (stages 1-2): no senescence regardless of LAI.
	if stage < 3:
		return 0.0
	var expected_lai: float = lerpf(5.5, 3.0, grain_frac)
	var sen: float = clampf(1.0 - lai / maxf(expected_lai, 0.1), 0.0, 1.0)
	sen *= clampf(grain_frac * 2.0, 0.0, 1.0)
	return sen


static func _build_individual_plants(
	container: Node3D,
	crop_key: String,
	grid: Vector2i,
	col: int,
	row: int,
	s: float,
	growth: float,
	senescence: float,
	stresses: Dictionary,
	grain_frac: float,
	tile_size: float,
	stunt: float = 1.0,
	collapse_y: float = 1.0,
) -> void:
	for hi in range(grid.x):
		var u: float = (float(hi) + 0.5) / float(grid.x)
		for vi in range(grid.y):
			var v: float = (float(vi) + 0.5) / float(grid.y)
			var lx: float = (u - 0.5) * tile_size
			var lz: float = (v - 0.5) * tile_size
			var sv: int = col * 7 + row * 13 + hi * 3 + vi * 5
			var jm: float = tile_size / float(grid.x) * 0.1
			var jx: float = (fmod(float(sv % 7), 3.0) - 1.5) * jm
			var jz: float = (fmod(float((sv * 3) % 5), 2.0) - 1.0) * jm
			var new_plant := create_3d_plant(crop_key, growth, senescence, stresses, grain_frac, sv)
			# Stunt scales XYZ uniformly; collapse only flattens Y.
			new_plant.scale = Vector3(s * stunt, s * stunt * collapse_y, s * stunt)
			new_plant.position = Vector3(lx + jx, 0, lz + jz)
			container.add_child(new_plant)


static func _build_baked_plants(
	# MultiMesh uses a single sample plant: per-leaf senescence gradient
	# is baked into materials at creation time (leaf_height set per leaf).
	# Per-instance variation is NOT possible — all instances share materials.
	container: Node3D,
	crop_key: String,
	grid: Vector2i,
	col: int,
	row: int,
	s: float,
	growth: float,
	senescence: float,
	stresses: Dictionary,
	grain_frac: float,
	tile_size: float,
	stunt: float = 1.0,
	collapse_y: float = 1.0,
) -> void:
	var sv_base: int = col * 7 + row * 13
	var sample_plant := create_3d_plant(crop_key, growth, senescence, stresses, grain_frac, sv_base)
	var meshes: Array[Dictionary] = []
	collect_meshes(sample_plant, Transform3D(), meshes)
	sample_plant.queue_free()
	if meshes.is_empty():
		return
	var total: int = grid.x * grid.y
	for entry: Dictionary in meshes:
		var layer_mm := MultiMesh.new()
		layer_mm.transform_format = MultiMesh.TRANSFORM_3D
		layer_mm.mesh = entry["mesh"]
		layer_mm.instance_count = total
		var local_t: Transform3D = entry["transform"]
		var i := 0
		for hi in range(grid.x):
			var u: float = (float(hi) + 0.5) / float(grid.x)
			for vi in range(grid.y):
				var v: float = (float(vi) + 0.5) / float(grid.y)
				var lx: float = (u - 0.5) * tile_size
				var lz: float = (v - 0.5) * tile_size
				var sv: int = sv_base + hi * 3 + vi * 5
				var jm: float = tile_size / float(grid.x) * 0.1
				var jx: float = (fmod(float(sv % 7), 3.0) - 1.5) * jm
				var jz: float = (fmod(float((sv * 3) % 5), 2.0) - 1.0) * jm
				var rot_y: float = CropRenderer3D.hash_val(sv, 0) * TAU
				var plant_t := Transform3D()
				plant_t = plant_t.scaled(Vector3(s * stunt, s * stunt * collapse_y, s * stunt))
				plant_t = plant_t.rotated(Vector3.UP, rot_y)
				plant_t.origin = Vector3(lx + jx, 0, lz + jz)
				layer_mm.set_instance_transform(i, plant_t * local_t)
				i += 1
		var layer_mmi := MultiMeshInstance3D.new()
		layer_mmi.multimesh = layer_mm
		if entry["material"]:
			layer_mmi.material_override = entry["material"]
		layer_mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		container.add_child(layer_mmi)


static func collect_meshes(
	node: Node, parent_transform: Transform3D, out: Array[Dictionary]
) -> void:
	var t: Transform3D = parent_transform * node.transform if node is Node3D else parent_transform
	if node is MeshInstance3D:
		var mi: MeshInstance3D = node as MeshInstance3D
		if mi.mesh:
			out.append({"mesh": mi.mesh, "material": mi.material_override, "transform": t})
	for child in node.get_children():
		collect_meshes(child, t, out)


static func create_3d_plant(
	crop_key: String,
	growth: float,
	senescence: float,
	stresses: Dictionary,
	grain_frac: float,
	seed_val: int,
) -> Node3D:
	match crop_key:
		"maize":
			return MaizeRenderer3D.create_plant(growth, senescence, stresses, grain_frac, seed_val)
		"spring_wheat", "winter_wheat":
			return WheatRenderer3D.create_plant(growth, senescence, stresses, grain_frac, seed_val)
		"sorghum":
			return SorghumRenderer3D.create_plant(
				growth, senescence, stresses, grain_frac, seed_val
			)
		"rice":
			return RiceRenderer3D.create_plant(growth, senescence, stresses, grain_frac, seed_val)
		"grape":
			return GrapeRenderer3D.create_plant(growth, senescence, stresses, grain_frac, seed_val)
		_:
			return MaizeRenderer3D.create_plant(growth, senescence, stresses, grain_frac, seed_val)
