extends RefCounted
## Procedural 3D grape renderer.
## Short trunk, broad palmate leaves, sphere berry clusters.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const TRUNK_HEIGHT := 1.5
const LEAF_SIZE := 0.15
const MAX_LEAVES := 6
const BERRY_RADIUS := 0.03


static func create_plant(
	growth_progress: float,
	senescence: float,
	stresses: Dictionary,
	grain_frac: float,
	seed_val: int,
) -> Node3D:
	var plant := Node3D.new()
	if growth_progress < 0.05:
		return plant

	var h: float = TRUNK_HEIGHT * clampf(growth_progress * 1.5, 0.0, 1.0)
	# Per-leaf materials created in loop for bottom-up senescence
	# Short trunk
	var trunk := MeshInstance3D.new()
	trunk.mesh = CR.create_stem_mesh(h, 0.004, 0.003)
	trunk.material_override = CR.create_stem_material(senescence, 0.1)
	trunk.position = Vector3(0, h * 0.5, 0)
	trunk.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	plant.add_child(trunk)
	# Broad palmate leaves — spread outward
	var num_leaves: int = int(clampf(growth_progress, 0.0, 1.0) * MAX_LEAVES)
	for li in range(num_leaves):
		var angle: float = float(li) / float(MAX_LEAVES) * TAU
		angle += CR.hash_val(seed_val, li * 3) * 0.5
		var tilt: float = 0.4 + CR.hash_val(seed_val, li * 3 + 1) * 0.4
		var dist: float = 0.08 + CR.hash_val(seed_val, li * 3 + 2) * 0.08
		var lx: float = cos(angle) * dist
		var lz: float = sin(angle) * dist
		var ly: float = h * (0.6 + float(li) * 0.05)
		var leaf := (
			CR
			. create_leaf_quad(
				LEAF_SIZE * growth_progress,
				LEAF_SIZE * growth_progress,
				Vector3.ZERO,
				Vector3.ZERO,
			)
		)
		var leaf_h: float = clampf(ly / maxf(h, 0.01), 0.0, 1.0)
		leaf.material_override = CR.create_leaf_material("grape", senescence, stresses, leaf_h)
		leaf.position = Vector3(lx, ly, lz)
		leaf.rotation = Vector3(-tilt, angle, 0)
		plant.add_child(leaf)
	# Berry clusters
	if grain_frac > 0.01 and growth_progress > 0.5:
		for ci in range(2):
			var cx: float = (CR.hash_val(seed_val, 40 + ci) - 0.5) * 0.1
			var cz: float = (CR.hash_val(seed_val, 42 + ci) - 0.5) * 0.1
			var berry := MeshInstance3D.new()
			var berry_mesh := SphereMesh.new()
			berry_mesh.radius = BERRY_RADIUS * grain_frac
			berry_mesh.height = BERRY_RADIUS * 2.0 * grain_frac
			berry_mesh.radial_segments = 6
			berry_mesh.rings = 3
			berry.mesh = berry_mesh
			var berry_mat := StandardMaterial3D.new()
			berry_mat.albedo_color = Color(0.3, 0.15, 0.4).lerp(Color(0.5, 0.2, 0.55), grain_frac)
			berry_mat.roughness = 0.5
			berry.material_override = berry_mat
			berry.position = Vector3(cx, h * 0.5, cz)
			berry.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(berry)

	return plant
