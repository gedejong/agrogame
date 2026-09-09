class_name CropVisuals
extends RefCounted
## 3D crop rendering: maps simulation state (stage, LAI, grain, development
## stage) onto renderer inputs, instances plants per tile, and bakes
## high-density crops into MultiMeshes.
##
## Renderer inputs, all in [0, 1]:
##   growth     — canopy size / stem elongation (0 = nothing, 1 = full size)
##   senescence — canopy yellowing and dieback
##   repro      — reproductive progress: 0 until heading, 1 at ripe maturity.
##                Drives organ emergence (tassel, ear, spike, panicle, cluster)
##                and organ colour, independent of how much grain actually set.
##   yield_frac — how well grain filled relative to the crop's reference yield.
##                Scales organ size only, so a starved crop shows small ears
##                rather than none.

## Fallback LAI ceiling for crops without an entry in CROP_LAI_MAX.
const MAX_LAI := 6.0

## Per-crop LAI ceiling for normalising canopy size (matches lai_max in the
## crop presets under data/crops).
const CROP_LAI_MAX := {
	"maize": 6.0,
	"winter_wheat": 7.0,
	"spring_wheat": 6.0,
	"rice": 8.0,
	"sorghum": 5.0,
	"grape": 4.0,
}

## Grain mass (g/m²) that counts as a full yield for organ sizing. Crops with
## no simulated grain (grape) always render full-size organs.
const CROP_GRAIN_REF := {
	"maize": 800.0,
	"winter_wheat": 700.0,
	"spring_wheat": 600.0,
	"rice": 700.0,
	"sorghum": 400.0,
	"grape": 0.0,
}

## How strongly ripening (development stage past anthesis) yellows the canopy
## on top of measured LAI loss. Sorghum is a stay-green type; grape leaves stay
## green while the fruit ripens.
const RIPENING_SENESCENCE := {
	"sorghum": 0.7,
	"grape": 0.0,
}

## Development stage (0 sowing, 1 anthesis, 2 maturity) at which reproductive
## organs first become visible (heading / tassel emergence / bloom).
const HEADING_DVS := 0.92
## Fraction of the anthesis→maturity interval before ripening starts to colour
## the canopy (grain fill runs green for its first third).
const RIPENING_ONSET := 0.35
## Minimum stem elongation at anthesis as a fraction of full height, so a
## sparse canopy (low LAI) still shows a fully elongated stem after heading.
const DEV_HEIGHT_FLOOR := 0.7
## Peak LAI assumed when no LAI history is available, as a fraction of lai_max.
const FALLBACK_PEAK_FRAC := 0.75

## Maximum stem-lean tilt at full lodging (~34°). A lean is a pure rotation
## (determinant 1): it never scales an axis to 0, so the instance transform
## stays non-degenerate. Ref: Berry et al. 2004 — severe lodging tips stems >30°.
const LODGE_MAX_TILT_RAD := 0.6

## Placement scatter as a fraction of the plant spacing along each axis:
## drills and planters never drop seed on an exact lattice, and a regular
## lattice is the strongest "copied plant" cue in a rendered stand.
const PLACEMENT_JITTER := 0.5
## Slight stem lean (rad, maximum) that every plant carries in a random
## direction, lodged or not; identical vertical stems read as copies.
const NATURAL_LEAN_RAD := 0.06
## Per-instance size scatter (+/- fraction) of a baked stand. Instances of
## one sample plant share geometry, so stand heterogeneity in height and
## vigour is expressed as a uniform scale instead.
const VIGOUR_SCATTER := 0.12
## Distinct sample plants baked per tile; each instance draws one of them
## so a dense stand is not a single plant repeated.
const BAKED_VARIANTS := 2
## Stem flexibility per crop for the wind bend: 0 a vine tied to its wires,
## 1 a thin cereal culm.
const PLANT_FLEX := {
	"maize": 0.35,
	"spring_wheat": 1.0,
	"winter_wheat": 1.0,
	"sorghum": 0.5,
	"rice": 1.0,
	"grape": 0.0,
}
## Hash stream of a plant's wind jitter, its own random number in the wind
## shaders (plant_jitter on an individual plant, custom data on a baked one).
const WIND_JITTER_IDX := 120

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
	var plants: Array = crop_sprites
	var vis: Dictionary = derive_visual_state(tile_data)
	var growth: float = vis["growth"]
	var senescence: float = vis["senescence"]
	var repro: float = vis["repro"]
	var yield_frac: float = vis["yield_frac"]
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
	# Morphological stress effects: Zn deficiency stunts the whole plant
	# uniformly; severe drought during late senescence lodges it (a tilt, pure
	# rotation, per plant). Ripening never changes a plant's height: dry
	# culms stand until harvest.
	var stunt: float = StressUtils.calc_stunt_factor(stresses)
	var lodging: float = StressUtils.calc_lodging_factor(stresses, senescence)
	# Bake to a MultiMesh above this count so agronomic maize (40/tile) still
	# renders as a few GPU-instanced draws rather than ~40 discrete node trees.
	if total_plants > 35:
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
			repro,
			tile_size,
			stunt,
			lodging,
			yield_frac,
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
			repro,
			tile_size,
			stunt,
			lodging,
			yield_frac,
		)


static func derive_visual_state(tile_data: Dictionary) -> Dictionary:
	"""Map one tile's simulation fields to renderer inputs.

	Reads crop_key, crop_stage (int), lai, grain_g_m2 and, when present,
	dev_stage (WOFOST DVS from the API) and lai_peak (season-to-date LAI
	maximum tracked by the view). Missing dev_stage / lai_peak fall back to
	stage-based nominal values so saved games and tests without them still
	render sensibly."""
	var crop_key: String = tile_data.get("crop_key", "")
	var stage: int = int(tile_data.get("crop_stage", 0))
	var lai: float = float(tile_data.get("lai", 0.0))
	var grain: float = float(tile_data.get("grain_g_m2", 0.0))
	var dev_stage: float = float(tile_data.get("dev_stage", -1.0))
	var lai_peak: float = float(tile_data.get("lai_peak", -1.0))
	var lai_max: float = float(CROP_LAI_MAX.get(crop_key, MAX_LAI))
	var grain_ref: float = float(CROP_GRAIN_REF.get(crop_key, 800.0))
	var grain_frac: float = clampf(grain / grain_ref, 0.0, 1.0) if grain_ref > 0.0 else 1.0
	var ripening_weight: float = float(RIPENING_SENESCENCE.get(crop_key, 1.0))
	var lai_frac: float = clampf(lai / lai_max, 0.0, 1.0)
	var lai_peak_frac: float = clampf(lai_peak / lai_max, 0.0, 1.0) if lai_peak > 0.0 else -1.0
	return {
		"growth": _calc_growth(stage, lai_frac, grain_frac, dev_stage, lai_peak_frac),
		"senescence":
		_calc_senescence(stage, lai, grain_frac, dev_stage, lai_peak, lai_max, ripening_weight),
		"repro": _calc_repro(stage, grain_frac, dev_stage),
		"yield_frac": grain_frac,
	}


static func _nominal_dev_stage(stage: int, grain_frac: float) -> float:
	## Stand-in development stage when the API did not supply one: the middle
	## of each discrete stage, with grain fill progressing by grain mass.
	match stage:
		0:
			return 0.0
		1:
			return 0.15
		2:
			return 0.6
		3:
			return 1.05
		_:
			return 1.0 + clampf(0.3 + grain_frac * 0.7, 0.0, 1.0)


static func _calc_growth(
	stage: int,
	lai_frac: float,
	grain_frac: float,
	dev_stage: float = -1.0,
	lai_peak_frac: float = -1.0,
) -> float:
	## Canopy size in [0, 1]. Height ∝ sqrt(LAI): leaf area scales with
	## height² (more + bigger leaves), so doubling LAI gives ~40% more height.
	## Stems never shrink: size is taken from the season's peak LAI, and once
	## the crop has headed the stem is at least DEV_HEIGHT_FLOOR of full height
	## however thin the canopy (grain fill sheds leaf area, not stem).
	if stage == 0:
		return 0.0
	var dvs: float = dev_stage if dev_stage >= 0.0 else _nominal_dev_stage(stage, grain_frac)
	var size_frac: float = maxf(clampf(lai_frac, 0.0, 1.0), clampf(lai_peak_frac, 0.0, 1.0))
	var base: float = sqrt(size_frac)
	# Floor: emerged plants have at least 5% even at LAI~0
	var floor_val: float = 0.05
	var elongation: float = DEV_HEIGHT_FLOOR * clampf(dvs, 0.0, 1.0)
	return clampf(maxf(maxf(base, floor_val), elongation), 0.0, 1.0)


static func _calc_repro(stage: int, grain_frac: float, dev_stage: float = -1.0) -> float:
	## Reproductive progress in [0, 1]: 0 before heading (HEADING_DVS), 1 at
	## maturity (DVS 2). Vegetative stages are always 0.
	if stage == 0:
		return 0.0
	var dvs: float = dev_stage if dev_stage >= 0.0 else _nominal_dev_stage(stage, grain_frac)
	if stage < 3:
		dvs = minf(dvs, 0.99)
	return clampf((dvs - HEADING_DVS) / (2.0 - HEADING_DVS), 0.0, 1.0)


static func _calc_senescence(
	stage: int,
	lai: float,
	grain_frac: float,
	dev_stage: float = -1.0,
	lai_peak: float = -1.0,
	lai_max: float = MAX_LAI,
	ripening_weight: float = 1.0,
) -> float:
	## Canopy senescence in [0, 1] from flowering onward, combining measured
	## leaf-area loss against the season peak with ripening (development past
	## anthesis, weighted per crop for stay-green types). Vegetative stages
	## never senesce regardless of LAI.
	if stage < 3:
		return 0.0
	var dvs: float = dev_stage if dev_stage >= 0.0 else _nominal_dev_stage(stage, grain_frac)
	var peak: float = lai_peak if lai_peak > 0.0 else FALLBACK_PEAK_FRAC * lai_max
	peak = maxf(maxf(peak, lai), 0.1)
	var canopy_loss: float = clampf(1.0 - lai / peak, 0.0, 1.0)
	var ripening: float = smoothstep(RIPENING_ONSET, 1.0, clampf(dvs - 1.0, 0.0, 1.0))
	ripening *= clampf(ripening_weight, 0.0, 1.0)
	return clampf(1.0 - (1.0 - canopy_loss) * (1.0 - ripening), 0.0, 1.0)


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
	repro: float,
	tile_size: float,
	stunt: float = 1.0,
	lodging: float = 0.0,
	yield_frac: float = 1.0,
) -> void:
	for hi in range(grid.x):
		var u: float = (float(hi) + 0.5) / float(grid.x)
		for vi in range(grid.y):
			var v: float = (float(vi) + 0.5) / float(grid.y)
			var lx: float = (u - 0.5) * tile_size
			var lz: float = (v - 0.5) * tile_size
			var sv: int = plant_seed(col, row, hi, vi)
			var jitter: Vector2 = _plant_offset(sv, grid, tile_size)
			var new_plant := create_3d_plant(
				crop_key, growth, senescence, stresses, repro, sv, yield_frac
			)
			# Stunt scales the plant uniformly.
			var plant_basis := Basis.from_scale(Vector3.ONE * (s * stunt))
			# Lodging tilt about the plant base: pure rotation, never degenerate.
			plant_basis = _lean_basis(sv, lodging) * natural_lean_basis(sv) * plant_basis
			new_plant.transform = Transform3D(plant_basis, Vector3(lx + jitter.x, 0, lz + jitter.y))
			container.add_child(new_plant)


static func _build_baked_plants(
	# MultiMesh instances of one sample plant share geometry and materials
	# (the per-leaf senescence gradient is baked into the sample). Variety
	# comes from a few sample variants mixed across the tile plus per-instance
	# yaw, size, lean and placement scatter.
	container: Node3D,
	crop_key: String,
	grid: Vector2i,
	col: int,
	row: int,
	s: float,
	growth: float,
	senescence: float,
	stresses: Dictionary,
	repro: float,
	tile_size: float,
	stunt: float = 1.0,
	lodging: float = 0.0,
	yield_frac: float = 1.0,
) -> void:
	var variants: Array[Array] = []
	for k in range(BAKED_VARIANTS):
		# Sample seeds sit outside the tile's own plant seeds (hi >= grid.x).
		var sample_seed: int = plant_seed(col, row, grid.x + k, 0)
		var sample_plant := create_3d_plant(
			crop_key, growth, senescence, stresses, repro, sample_seed, yield_frac
		)
		var meshes: Array[Dictionary] = []
		collect_meshes(sample_plant, Transform3D(), meshes)
		sample_plant.queue_free()
		variants.append(meshes)
	if variants[0].is_empty():
		return
	var placements: Array[Array] = _baked_placements(grid, col, row, s, tile_size, stunt, lodging)
	for k in range(BAKED_VARIANTS):
		var plants: Array = placements[k]
		if plants.is_empty():
			continue
		for entry: Dictionary in variants[k]:
			var layer_mm := MultiMesh.new()
			layer_mm.transform_format = MultiMesh.TRANSFORM_3D
			# The sample's material carries the wind frame shared by all plants
			# of the layer; the custom data carries each plant's own wind jitter
			# (INSTANCE_CUSTOM.r), so the material's own jitter is zero.
			layer_mm.use_custom_data = true
			layer_mm.mesh = entry["mesh"]
			layer_mm.instance_count = plants.size()
			var local_t: Transform3D = entry["transform"]
			for i in range(plants.size()):
				var placement: Dictionary = plants[i]
				var plant_t: Transform3D = placement["transform"]
				layer_mm.set_instance_transform(i, plant_t * local_t)
				layer_mm.set_instance_custom_data(i, Color(placement["jitter"], 0.0, 0.0, 0.0))
			var layer_mmi := MultiMeshInstance3D.new()
			layer_mmi.multimesh = layer_mm
			var material: Material = entry["material"]
			if material is ShaderMaterial:
				(material as ShaderMaterial).set_shader_parameter("plant_jitter", 0.0)
			if material:
				layer_mmi.material_override = material
			layer_mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			container.add_child(layer_mmi)


static func _baked_placements(
	grid: Vector2i, col: int, row: int, s: float, tile_size: float, stunt: float, lodging: float
) -> Array[Array]:
	## Placements of one tile's plants grouped by the sample variant each
	## draws, as {"transform": Transform3D, "jitter": float}: the variant is
	## hashed per plant so the mix has no lattice, the jitter is the plant's
	## random number for the wind shaders.
	var placements: Array[Array] = []
	for k in range(BAKED_VARIANTS):
		placements.append([])
	for hi in range(grid.x):
		var u: float = (float(hi) + 0.5) / float(grid.x)
		for vi in range(grid.y):
			var v: float = (float(vi) + 0.5) / float(grid.y)
			var lx: float = (u - 0.5) * tile_size
			var lz: float = (v - 0.5) * tile_size
			var sv: int = plant_seed(col, row, hi, vi)
			var jitter: Vector2 = _plant_offset(sv, grid, tile_size)
			var k: int = mini(
				int(CropRenderer3D.hash_val(sv, 92) * float(BAKED_VARIANTS)), BAKED_VARIANTS - 1
			)
			var plant_basis := _baked_instance_basis(sv, s, stunt, lodging)
			(
				placements[k]
				. append(
					{
						"transform":
						Transform3D(plant_basis, Vector3(lx + jitter.x, 0, lz + jitter.y)),
						"jitter": CropRenderer3D.hash_val(sv, WIND_JITTER_IDX),
					}
				)
			)
	return placements


static func plant_seed(col: int, row: int, hi: int, vi: int) -> int:
	## Seed of one plant, unique across the field for grids up to 64 x 64
	## plants per tile and 128 tile rows, so no two plants share a hash stream.
	return (col * 128 + row) * 4096 + hi * 64 + vi


static func _plant_offset(seed_val: int, grid: Vector2i, tile_size: float) -> Vector2:
	## Placement scatter of one plant, hashed, within PLACEMENT_JITTER of the
	## spacing along each axis (x, z).
	var dx: float = tile_size / float(grid.x) * PLACEMENT_JITTER
	var dz: float = tile_size / float(grid.y) * PLACEMENT_JITTER
	return Vector2(
		(CropRenderer3D.hash_val(seed_val, 90) - 0.5) * dx,
		(CropRenderer3D.hash_val(seed_val, 91) - 0.5) * dz
	)


static func _baked_instance_basis(seed_val: int, s: float, stunt: float, lodging: float) -> Basis:
	"""Per-instance orientation for MultiMesh baking: the stunt scale with
	the hashed vigour scatter, yaw jitter, the natural lean and the lodging
	lean composed into one basis. Extracted so the baked path stays
	unit-testable — MultiMesh instance transforms don't read back without a
	live RenderingServer (headless). Leans are rotations, so the determinant
	equals the scale product and is never 0 (non-degenerate)."""
	var vigour: float = 1.0 + (CropRenderer3D.hash_val(seed_val, 4) - 0.5) * 2.0 * VIGOUR_SCATTER
	var scale := Basis.from_scale(Vector3.ONE * (s * stunt * vigour))
	var rot_y: float = CropRenderer3D.hash_val(seed_val, 0) * TAU
	var yawed := Basis(Vector3.UP, rot_y) * scale
	return _lean_basis(seed_val, lodging) * natural_lean_basis(seed_val) * yawed


static func natural_lean_basis(seed_val: int) -> Basis:
	"""Slight stem lean every plant carries: a rotation (determinant 1) of up
	to NATURAL_LEAN_RAD about a horizontal axis, tilt and azimuth hashed per
	plant so no two neighbours lean alike."""
	var tilt: float = CropRenderer3D.hash_val(seed_val, 2) * NATURAL_LEAN_RAD
	var yaw: float = CropRenderer3D.hash_val(seed_val, 3) * TAU
	var axis := Vector3(cos(yaw), 0.0, -sin(yaw))
	return Basis(axis, tilt)


static func _lean_basis(seed_val: int, lodging: float) -> Basis:
	"""Stem-lean rotation for lodging. Identity when not lodging, so upright
	plants are untouched. The lean is a rotation about a horizontal axis
	(determinant 1) — it never scales an axis to 0, so the combined transform
	is never degenerate. Lean azimuth is hashed per plant from the
	col/row/plant seed, so neighbours fall in varied directions."""
	if lodging <= 0.0:
		return Basis.IDENTITY
	var yaw: float = CropRenderer3D.hash_val(seed_val, 1) * TAU
	var tilt: float = clampf(lodging, 0.0, 1.0) * LODGE_MAX_TILT_RAD
	# Tilt axis: horizontal, perpendicular to the lean azimuth (unit length).
	var axis := Vector3(cos(yaw), 0.0, -sin(yaw))
	return Basis(axis, tilt)


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
	repro: float,
	seed_val: int,
	yield_frac: float = 1.0,
) -> Node3D:
	var plant: Node3D
	match crop_key:
		"maize":
			plant = MaizeRenderer3D.create_plant(
				growth, senescence, stresses, repro, seed_val, yield_frac
			)
		"spring_wheat", "winter_wheat":
			plant = WheatRenderer3D.create_plant(
				growth, senescence, stresses, repro, seed_val, yield_frac
			)
		"sorghum":
			plant = SorghumRenderer3D.create_plant(
				growth, senescence, stresses, repro, seed_val, yield_frac
			)
		"rice":
			plant = RiceRenderer3D.create_plant(
				growth, senescence, stresses, repro, seed_val, yield_frac
			)
		"grape":
			plant = GrapeRenderer3D.create_plant(
				growth, senescence, stresses, repro, seed_val, yield_frac
			)
		_:
			plant = MaizeRenderer3D.create_plant(
				growth, senescence, stresses, repro, seed_val, yield_frac
			)
	CropRenderer3D.stamp_wind_frame(
		plant, PLANT_FLEX.get(crop_key, 0.5), CropRenderer3D.hash_val(seed_val, WIND_JITTER_IDX)
	)
	return plant
