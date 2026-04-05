extends RefCounted
## Procedural 3D sorghum renderer.
## Thick stem, broad drooping leaves, dense spherical seed head.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const STEM_HEIGHT := 2.0
const LEAF_WIDTH := 0.07
const LEAF_LENGTH := 0.7
const MAX_LEAVES := 8
const HEAD_RADIUS := 0.06


static func create_plant(
	growth_progress: float,
	senescence: float,
	stress: float,
	grain_frac: float,
	seed_val: int,
) -> Node3D:
	var plant := Node3D.new()
	if growth_progress < 0.05:
		return plant

	var h: float = STEM_HEIGHT * growth_progress
	var leaf_mat := CR.create_leaf_material("sorghum", senescence, stress)
	# Thick stem
	var stem := MeshInstance3D.new()
	stem.mesh = CR.create_stem_mesh(h, 0.02, 0.01)
	stem.material_override = CR.create_stem_material(senescence)
	stem.position = Vector3(0, h * 0.5, 0)
	stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	plant.add_child(stem)
	# Broad drooping leaves — alternating ~120° like maize
	var num_leaves: int = int(clampf(growth_progress, 0.0, 1.0) * MAX_LEAVES)
	for li in range(num_leaves):
		var frac: float = float(li) / float(MAX_LEAVES)
		var y: float = (0.1 + frac * 0.7) * h
		var azimuth: float = float(li) * TAU / 3.0 + (CR.hash_val(seed_val, li * 3) - 0.5) * 0.7
		var droop: float = 0.4 + (1.0 - frac) * 0.6
		var pivot := Node3D.new()
		pivot.position = Vector3(0, y, 0)
		pivot.rotation.y = azimuth
		var leaf := CR.create_leaf_quad(
			LEAF_WIDTH, LEAF_LENGTH * growth_progress, Vector3.ZERO, Vector3.ZERO
		)
		leaf.material_override = leaf_mat
		leaf.position = Vector3(0, 0, LEAF_LENGTH * growth_progress * 0.4)
		leaf.rotation.x = -droop
		pivot.add_child(leaf)
		plant.add_child(pivot)
	# Dense spherical seed head
	if grain_frac > 0.01 and growth_progress > 0.7:
		var head := MeshInstance3D.new()
		var head_mesh := SphereMesh.new()
		head_mesh.radius = HEAD_RADIUS * grain_frac
		head_mesh.height = HEAD_RADIUS * 2.0 * grain_frac
		head_mesh.radial_segments = 8
		head_mesh.rings = 4
		head.mesh = head_mesh
		head.material_override = CR.create_grain_material(grain_frac)
		head.position = Vector3(0, h + HEAD_RADIUS, 0)
		head.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(head)

	return plant
