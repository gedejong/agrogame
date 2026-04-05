extends RefCounted
## Procedural 3D maize renderer.
## Tapered stem, arc-shaped leaves with alpha mask, ear at 2/3 height.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const MAX_LEAVES := 10
const STEM_HEIGHT := 2.5
const STEM_RADIUS_BOTTOM := 0.015
const STEM_RADIUS_TOP := 0.008
const LEAF_WIDTH := 0.08
const LEAF_LENGTH := 0.8
const EAR_RADIUS := 0.025
const EAR_HEIGHT := 0.15


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
	# Stem — radius grows with maturity
	var r_bot: float = STEM_RADIUS_BOTTOM * growth_progress + 0.002
	var r_top: float = STEM_RADIUS_TOP * growth_progress + 0.001
	var stem_mesh := CR.create_stem_mesh(h, r_bot, r_top)
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
		var ear_x: float = ear_side * 0.04
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
	var segs := 5
	for li in range(num_leaves):
		var frac: float = float(li) / float(MAX_LEAVES)
		var hi := li * 7
		var y_frac: float = 0.05 + frac * 0.8
		var y: float = y_frac * stem_h
		# Bell-curve leaf length: longest at ~55% stem height, shorter at top/bottom.
		# len_curve peaks at frac=0.55, ranges 0→1→0
		var len_curve: float = maxf(1.0 - 4.0 * (frac - 0.55) * (frac - 0.55), 0.0)
		var len_var: float = (CR.hash_val(seed_val, hi) - 0.5) * 0.2
		# Base length from position on stem (short→long→short)
		var base_len: float = LEAF_LENGTH * (0.3 + len_curve * 0.7) * (1.0 + len_var)
		# Leaf maturity: each leaf matures as overall plant grows.
		# Bottom leaves mature first, top leaves last.
		# leaf_maturity=0 (just emerging) → 1 (fully grown)
		var leaf_appear: float = frac * 0.8
		var leaf_maturity: float = clampf(
			(growth_progress - leaf_appear) / maxf(1.0 - leaf_appear, 0.01), 0.0, 1.0
		)
		var leaf_len: float = base_len * leaf_maturity
		var leaf_w: float = LEAF_WIDTH * (0.5 + len_curve * 0.5) * leaf_maturity
		if leaf_len < 0.01:
			continue
		# ~120° phyllotaxis + random variation
		var azimuth: float = float(li) * TAU / 3.0
		azimuth += (CR.hash_val(seed_val, hi + 1) - 0.5) * 0.8
		# Droop depends on both leaf length AND maturity:
		# Short/young leaves point up, long mature leaves droop.
		# len_curve drives potential droop (long leaves can droop more).
		# leaf_maturity drives actual droop (young leaves still upright).
		var droop_potential: float = len_curve * 0.8
		var droop_var: float = (CR.hash_val(seed_val, hi + 2) - 0.5) * 0.2
		var droop: float = droop_potential * leaf_maturity * (0.8 + droop_var)
		# Build curved leaf
		var pivot := Node3D.new()
		pivot.position = Vector3(0, y, 0)
		pivot.rotation.y = azimuth
		var leaf_mesh := _build_curved_leaf(leaf_len, leaf_w, droop, segs)
		var leaf_inst := MeshInstance3D.new()
		leaf_inst.mesh = leaf_mesh
		leaf_inst.material_override = leaf_mat
		leaf_inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		pivot.add_child(leaf_inst)
		plant.add_child(pivot)


static func _build_curved_leaf(
	length: float, width: float, droop: float, segments: int
) -> ArrayMesh:
	## Build a leaf as a curved quad strip. The leaf starts at the stem
	## going slightly up, extends outward, then droops at the tip.
	## Shape: y = -droop * t^2 + rise * t, where t goes 0→1 along length.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	var rise: float = length * 0.3
	for si in range(segments + 1):
		var t: float = float(si) / float(segments)
		# Width narrows: wide in middle, narrow at base and tip
		var w_frac: float = 4.0 * t * (1.0 - t)
		var hw: float = width * 0.5 * w_frac
		# Arc: up then droop. y = rise * 4t(1-t) - droop * t^3
		var arc_y: float = rise * 4.0 * t * (1.0 - t) - droop * length * t * t * t
		var out_z: float = length * t
		# UV: t along length, 0/1 across width
		st.set_uv(Vector2(t, 0.0))
		st.add_vertex(Vector3(-hw, arc_y, out_z))
		st.set_uv(Vector2(t, 1.0))
		st.add_vertex(Vector3(hw, arc_y, out_z))
	st.generate_normals()
	return st.commit()
