extends RefCounted
## Procedural 3D maize renderer.
## Tapered stem, arc-shaped leaves with alpha mask, ear at 2/3 height.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const MAX_LEAVES := 10
const STEM_HEIGHT := 0.25
const STEM_RADIUS_BOTTOM := 0.004
const STEM_RADIUS_TOP := 0.002
const LEAF_WIDTH := 0.04
const LEAF_LENGTH := 0.08
const EAR_RADIUS := 0.008
const EAR_HEIGHT := 0.025


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
	# Stem
	var stem_mesh := CR.create_stem_mesh(h, STEM_RADIUS_BOTTOM, STEM_RADIUS_TOP)
	var stem_mat := CR.create_stem_material(senescence)
	var stem := MeshInstance3D.new()
	stem.mesh = stem_mesh
	stem.material_override = stem_mat
	stem.position = Vector3(0, h * 0.5, 0)
	stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	plant.add_child(stem)

	# Leaves
	var num_leaves: int = int(clampf(growth_progress, 0.0, 1.0) * MAX_LEAVES)
	if num_leaves > 0:
		var leaf_mat := CR.create_leaf_material("maize", senescence, stress)
		_add_leaves(plant, num_leaves, h, growth_progress, senescence, seed_val, leaf_mat)

	# Ear/grain at 2/3 stem height
	if grain_frac > 0.01 and growth_progress > 0.7:
		var ear_mesh := CylinderMesh.new()
		ear_mesh.height = EAR_HEIGHT * grain_frac
		ear_mesh.bottom_radius = EAR_RADIUS
		ear_mesh.top_radius = EAR_RADIUS * 0.7
		ear_mesh.radial_segments = 6
		var ear_mat := CR.create_grain_material(grain_frac)
		var ear := MeshInstance3D.new()
		ear.mesh = ear_mesh
		ear.material_override = ear_mat
		# Offset ear to side + hash variation
		var ear_side: float = -1.0 if CR.hash_val(seed_val, 50) > 0.5 else 1.0
		var ear_x: float = ear_side * 0.008
		ear.position = Vector3(ear_x, h * 0.67, 0)
		ear.rotation.z = ear_side * 0.3
		ear.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(ear)

	return plant


static func _add_leaves(
	plant: Node3D,
	num_leaves: int,
	stem_h: float,
	growth_progress: float,
	_senescence: float,
	seed_val: int,
	leaf_mat: ShaderMaterial,
) -> void:
	for li in range(num_leaves):
		var frac: float = float(li) / float(MAX_LEAVES)
		var hi := li * 7
		# Position along stem
		var y_frac: float = 0.05 + frac * 0.8
		var y: float = y_frac * stem_h
		# Alternating sides
		var dir: float = -1.0 if li % 2 == 0 else 1.0
		# Bell-curve leaf length: longest at 55% height
		var len_curve: float = 1.0 - 4.0 * (frac - 0.55) * (frac - 0.55)
		var len_var: float = (CR.hash_val(seed_val, hi) - 0.5) * 0.3
		var leaf_len: float = (
			LEAF_LENGTH * (0.5 + len_curve * 0.5) * (1.0 + len_var) * growth_progress
		)
		# Width varies with length
		var leaf_w: float = LEAF_WIDTH * (0.6 + len_curve * 0.4)
		# Facing angle (rotation around Y)
		var facing: float = CR.hash_val(seed_val, hi + 1) * TAU
		# Droop: lower leaves droop more
		var age: float = 1.0 - frac
		var droop: float = (0.3 + age * 0.8) * (1.0 + (CR.hash_val(seed_val, hi + 2) - 0.5) * 0.3)
		# Arc angle: leaves start vertical, tip droops
		var arc_angle: float = PI * 0.15 + droop * 0.4

		var leaf := CR.create_leaf_quad(leaf_w, leaf_len, Vector3.ZERO, Vector3.ZERO)
		leaf.material_override = leaf_mat
		# Each leaf radiates outward from stem at azimuthal angle
		# Spread evenly around stem + alternating + hash variation
		var base_angle: float = float(li) / float(num_leaves) * TAU
		base_angle += (CR.hash_val(seed_val, hi + 3) - 0.5) * 0.5
		var out_dist: float = leaf_len * 0.3
		var lx: float = cos(base_angle) * out_dist
		var lz: float = sin(base_angle) * out_dist
		leaf.position = Vector3(lx * 0.3, y, lz * 0.3)
		# Face outward from stem, tilt down for arc/droop
		leaf.rotation = Vector3(-arc_angle, base_angle, 0)
		plant.add_child(leaf)
