extends RefCounted
## Base class for 3D procedural crop renderers.
## Provides shared utilities: leaf strip and quad builders, stem builder,
## material factories, hash-based randomness and growth-to-colour mapping.

const LEAF_SHADER = preload("res://shaders/crop_leaf.gdshader")
const STEM_SHADER = preload("res://shaders/crop_stem.gdshader")
const ORGAN_SHADER = preload("res://shaders/crop_organ.gdshader")

const LEAF_MASKS := {
	"maize": preload("res://assets/textures/leaf_maize_alpha.png"),
	"wheat": preload("res://assets/textures/leaf_wheat_alpha.png"),
	"sorghum": preload("res://assets/textures/leaf_sorghum_alpha.png"),
	"rice": preload("res://assets/textures/leaf_rice_alpha.png"),
	"grape": preload("res://assets/textures/leaf_grape_alpha.png"),
}

## Mature blade colour per crop: sorghum carries a waxy blue-green bloom,
## rice is a brighter yellow-green, vine leaves a deeper matte green.
const LEAF_BASE_COLOR := {
	"maize": Color(0.20, 0.55, 0.15),
	"wheat": Color(0.22, 0.54, 0.20),
	"sorghum": Color(0.21, 0.50, 0.27),
	"rice": Color(0.25, 0.58, 0.17),
	"grape": Color(0.19, 0.48, 0.16),
}
## Strength of the pale midrib and parallel-vein shading on a blade; the
## palmate vine leaf is drawn without one.
const LEAF_MIDRIB := {"maize": 1.0, "wheat": 0.5, "sorghum": 1.0, "rice": 0.5, "grape": 0.0}
## Leaves that hang from a petiole: the wind swings them from their top edge
## (UV.y = 0) rather than from a collar along UV.x.
const LEAF_HANGING := {"grape": 1.0}
## A plant is never treated as shorter than this (m) when its wind bend is
## normalised, so a seedling does not whip.
const WIND_FRAME_MIN_HEIGHT := 0.05

const STEM_COLOR := Color(0.3, 0.5, 0.2)
const STEM_SENESCENT := Color(0.55, 0.45, 0.25)
const GRAIN_COLOR := Color(0.85, 0.75, 0.35)

## Leaf segment LOD: set by farm_view based on camera distance.
## Renderers read this to decide segment count.
static var leaf_segments: int = 5


class LeafShape:
	## Cross-section and 3D-curve modifiers for build_curved_leaf. The
	## defaults give a flat, straight blade whose width follows the parabola
	## 4t(1-t).
	## Position along the blade (0 collar, 1 tip) of maximum width; grass
	## blades are widest about a third of the way out. Negative keeps the
	## symmetric parabola.
	var peak: float = -1.0
	## Width at the collar as a fraction of the maximum width (peak >= 0 only).
	var base_frac: float = 0.5
	## Edge lift at the collar as a fraction of the half-width: the V-shaped
	## keel of a grass blade along its midrib, flattening towards the tip.
	var keel: float = 0.0
	## Rotation of the cross-section about the midrib at the tip (rad).
	var twist: float = 0.0
	## Sideways displacement of the tip as a fraction of blade length.
	var sway: float = 0.0


static func hash_val(seed_val: int, idx: int) -> float:
	## Deterministic pseudo-random float in [0, 1) for one plant (seed_val)
	## and one organ or trait (idx). Both inputs pass through an avalanche
	## hash, so neighbouring plants and successive leaves draw unrelated
	## values: a fixed stride between neighbours would repeat as a visible
	## pattern across a stand.
	var h: int = (seed_val * 0x9E3779B1 + idx * 0x85EBCA77) & 0xFFFFFFFF
	h = (((h >> 16) ^ h) * 0x45D9F3B) & 0xFFFFFFFF
	h = (((h >> 16) ^ h) * 0x45D9F3B) & 0xFFFFFFFF
	h = (h >> 16) ^ h
	return float(h & 0xFFFFFF) / 16777216.0


static func create_leaf_material(
	crop_key: String,
	senescence: float,
	stresses: Dictionary,
	leaf_height: float = 0.5,
	age: float = 1.0,
) -> ShaderMaterial:
	## Leaf shader material. leaf_height (0 bottom … 1 top) drives bottom-up
	## senescence; age (0 just emerged … 1 fully expanded) pales young leaves.
	var mat := ShaderMaterial.new()
	mat.shader = LEAF_SHADER
	var mask: Texture2D = LEAF_MASKS.get(crop_key, LEAF_MASKS["maize"])
	mat.set_shader_parameter("alpha_mask", mask)
	var base: Color = LEAF_BASE_COLOR.get(crop_key, LEAF_BASE_COLOR["maize"])
	mat.set_shader_parameter("base_color", Vector3(base.r, base.g, base.b))
	mat.set_shader_parameter("midrib", LEAF_MIDRIB.get(crop_key, 0.0))
	mat.set_shader_parameter("senescence", senescence)
	mat.set_shader_parameter("leaf_height", leaf_height)
	mat.set_shader_parameter("age", clampf(age, 0.0, 1.0))
	mat.set_shader_parameter("stress_water", stresses.get("water", 0.0))
	mat.set_shader_parameter("stress_n", stresses.get("n", 0.0))
	mat.set_shader_parameter("stress_p", stresses.get("p", 0.0))
	mat.set_shader_parameter("stress_fe", stresses.get("fe", 0.0))
	mat.set_shader_parameter("stress_zn", stresses.get("zn", 0.0))
	mat.set_shader_parameter("stress_frost", stresses.get("frost", 0.0))
	mat.set_shader_parameter("stress_heat", stresses.get("heat", 0.0))
	mat.set_shader_parameter("hanging", LEAF_HANGING.get(crop_key, 0.0))
	# Wind: phase offset desyncs leaf flutter. Use golden ratio for spread.
	# TODO: per-leaf materials are expensive (~500 at 36 tiles). Consider
	# shared materials with per-instance data for LOD at scale.
	mat.set_shader_parameter("wind_phase", fmod(leaf_height * 2.399, TAU))
	return mat


static func set_wind(plant: Node3D, strength: float, direction: Vector2) -> void:
	## Set wind on all ShaderMaterial children of a plant node.
	for child in plant.get_children():
		_set_wind_recursive(child, strength, direction)


static func _set_wind_recursive(node: Node, strength: float, dir: Vector2) -> void:
	if node is GeometryInstance3D:
		var gi: GeometryInstance3D = node as GeometryInstance3D
		if gi.material_override is ShaderMaterial:
			var sm: ShaderMaterial = gi.material_override as ShaderMaterial
			sm.set_shader_parameter("wind_strength", strength)
			sm.set_shader_parameter("wind_direction", dir)
	for child in node.get_children():
		_set_wind_recursive(child, strength, dir)


static func stamp_wind_frame(plant: Node3D, flex: float, jitter: float = 0.0) -> void:
	## Give every mesh of a freshly built plant the per-mesh data the crop
	## shaders bend it with (crop_wind.gdshaderinc), as uniforms of the mesh's
	## own material: the height of the whole plant, the height of the mesh
	## origin above the plant base, the species' stem flexibility and the
	## plant's own random number. Meshes without a wind shader (fixtures,
	## grain) are left alone. A material holds one origin height, so a renderer
	## gives meshes that stand at different heights their own materials; a mesh
	## found sharing its material with one at another height is reported as an
	## error and bends about that first mesh's base.
	var frames: Array[Array] = []
	_collect_mesh_frames(plant, Transform3D.IDENTITY, frames)
	var height: float = WIND_FRAME_MIN_HEIGHT
	for entry: Array in frames:
		height = maxf(height, entry[1])
	# Origin height stamped on each material so far.
	var stamped: Dictionary = {}
	for entry: Array in frames:
		var mi: MeshInstance3D = entry[0]
		var origin: float = entry[2]
		var mat: ShaderMaterial = mi.material_override as ShaderMaterial
		if mat == null:
			continue
		if stamped.has(mat):
			if not is_equal_approx(float(stamped[mat]), origin):
				push_error(
					(
						"%s: mesh %s at height %.3f shares its material with a mesh at %.3f"
						% [plant.name, mi.name, origin, float(stamped[mat])]
					)
				)
			continue
		stamped[mat] = origin
		mat.set_shader_parameter("plant_height", height)
		mat.set_shader_parameter("origin_height", origin)
		mat.set_shader_parameter("plant_flex", flex)
		mat.set_shader_parameter("plant_jitter", jitter)


static func _collect_mesh_frames(node: Node, parent_xf: Transform3D, out: Array[Array]) -> void:
	## Depth-first [mesh instance, top of its bounds, origin height] per mesh,
	## in the frame of the plant root.
	var xf: Transform3D = parent_xf
	if node is Node3D:
		xf = parent_xf * (node as Node3D).transform
	if node is MeshInstance3D:
		var mi: MeshInstance3D = node as MeshInstance3D
		var top: float = xf.origin.y
		if mi.mesh != null:
			top = (xf * mi.mesh.get_aabb()).end.y
		out.append([mi, top, maxf(xf.origin.y, 0.0)])
	for child in node.get_children():
		_collect_mesh_frames(child, xf, out)


static func leaf_segments_for_distance(cam_distance: float) -> int:
	## Return leaf segment count based on camera distance.
	## Close: 7 segments (smooth curves). Far: 3 segments (perf).
	if cam_distance < 3.0:
		return 7
	if cam_distance < 6.0:
		return 5
	return 3


static func stress_droop_bonus(stresses: Dictionary) -> float:
	## Extra droop from drought (wilting) and N deficiency (limp leaves).
	var water_s: float = stresses.get("water", 0.0)
	var n_s: float = stresses.get("n", 0.0)
	return clampf(water_s * 0.6 + n_s * 0.3, 0.0, 0.8)


static func create_stem_mesh(
	height: float, radius_bottom: float, radius_top: float
) -> CylinderMesh:
	var cyl := CylinderMesh.new()
	cyl.height = height
	cyl.bottom_radius = radius_bottom
	cyl.top_radius = radius_top
	cyl.radial_segments = 6
	cyl.rings = 4  # enough intermediate vertices for shader bend curve
	return cyl


static func create_stem_material(
	senescence: float, fresh: Color = STEM_COLOR, dry: Color = STEM_SENESCENT
) -> ShaderMaterial:
	## Flat-coloured stem material blending from its fresh to its dry colour
	## with senescence; the wind bend comes from the plant's instance data.
	var mat := ShaderMaterial.new()
	mat.shader = STEM_SHADER
	var color: Color = fresh.lerp(dry, clampf(senescence, 0.0, 1.0))
	mat.set_shader_parameter("stem_color", Vector3(color.r, color.g, color.b))
	return mat


static func create_grain_material(grain_frac: float) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = GRAIN_COLOR.darkened((1.0 - grain_frac) * 0.3)
	mat.roughness = 0.7
	return mat


static func create_organ_material(
	color: Color, roughness: float = 0.75, sway: float = 1.0, phase: float = 0.0
) -> ShaderMaterial:
	## Double-sided material for reproductive organs and fruit: color times the
	## mesh's vertex colours, carried by the plant's wind bend and swinging
	## about the mesh origin by sway (0 held fast against the culm, 1 a head
	## free on its peduncle) at the rhythm offset phase.
	var mat := ShaderMaterial.new()
	mat.shader = ORGAN_SHADER
	mat.set_shader_parameter("albedo", Vector3(color.r, color.g, color.b))
	mat.set_shader_parameter("roughness", roughness)
	mat.set_shader_parameter("sway", sway)
	mat.set_shader_parameter("wind_phase", fposmod(phase, TAU))
	return mat


static func create_fixture_material(color: Color, roughness: float = 0.75) -> StandardMaterial3D:
	## Plain double-sided material for fixed structures (posts, wires, trained
	## wood) that the wind leaves alone.
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = roughness
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	return mat


static func ripen_color(
	green: Color, ripe: Color, dry: Color, repro: float, senescence: float
) -> Color:
	## Organ colour along ripening: green while filling, the ripe colour by
	## late grain fill, then pulled toward dry/straw as the canopy senesces.
	var ripe_t: float = smoothstep(0.3, 0.9, repro)
	var color: Color = green.lerp(ripe, ripe_t)
	return color.lerp(dry, clampf(senescence, 0.0, 1.0) * 0.6)


static func organ_emergence(repro: float) -> float:
	## Heading / silking / bloom: organs unfold over the first 10% of
	## reproductive progress, so they are never at full size on day one.
	return smoothstep(0.0, 0.1, repro)


static func fill_scale(repro: float, yield_frac: float) -> float:
	## Organ size factor: organs appear at 60% of their final size and fill
	## to full size (scaled by how well grain actually set) by mid grain fill.
	var fill: float = smoothstep(0.1, 0.6, repro)
	var filled: float = lerpf(0.6, 1.0, clampf(yield_frac, 0.0, 1.0))
	return lerpf(0.6, filled, fill)


static func attach_mesh(
	parent: Node3D,
	mesh: Mesh,
	material: Material,
	pos: Vector3,
	rot: Vector3 = Vector3.ZERO,
) -> MeshInstance3D:
	## Add a shadow-casting MeshInstance3D under parent and return it.
	var inst := MeshInstance3D.new()
	inst.mesh = mesh
	inst.material_override = material
	inst.position = pos
	inst.rotation = rot
	inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	parent.add_child(inst)
	return inst


static func create_leaf_quad(
	width: float, length: float, offset: Vector3, rot: Vector3
) -> MeshInstance3D:
	## Flat quad for a single leaf. The node origin is the leaf's attachment,
	## which the wind swings it about; offset shifts the quad from it, so a
	## leaf hanging from its petiole sits below the origin.
	var quad := QuadMesh.new()
	quad.size = Vector2(width, length)
	quad.center_offset = offset
	var inst := MeshInstance3D.new()
	inst.mesh = quad
	inst.rotation = rot
	inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	return inst


static func build_curved_leaf(
	length: float,
	width: float,
	droop: float,
	segments: int = 5,
	base_width: float = 0.0,
	rise_frac: float = -1.0,
	shape: LeafShape = null,
) -> ArrayMesh:
	## Curved blade strip along +z from its collar at the origin.
	## Midrib: y = rise * 4t(1-t) - droop * length * t^3, so a low droop sends
	## the blade up and out while a high droop sags the tip.
	## Width follows the parabola 4t(1-t) unless shape sets a peak position;
	## base_width is the minimum width at t = 0, where a sheath wraps the stem.
	## rise_frac: arch height as a fraction of length. Negative selects the
	## default arch (0.3-0.6, falling with droop), suited to blades attached
	## near-horizontally; blades that are rotated steeply upright need a small
	## rise, otherwise the arch curls back over the stem.
	## shape adds a keeled cross-section, twist and sideways sway; each ring of
	## the strip has an edge, midrib and edge vertex so the keel fold renders.
	## UV.x runs collar to tip, UV.y edge to edge with the midrib at 0.5.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var rise: float = length * (0.3 + (1.0 - clampf(droop, 0.0, 1.0)) * 0.3)
	if rise_frac >= 0.0:
		rise = length * rise_frac
	var bw: float = maxf(base_width * 0.5, 0.0)
	var prev: Array[Vector3] = _leaf_ring(0.0, length, width, bw, rise, droop, shape)
	for si in range(segments):
		var t0: float = float(si) / float(segments)
		var t1: float = float(si + 1) / float(segments)
		var ring: Array[Vector3] = _leaf_ring(t1, length, width, bw, rise, droop, shape)
		var w0: float = prev[0].distance_to(prev[2])
		var w1: float = ring[0].distance_to(ring[2])
		# Skip degenerate segments where both ends are near-zero width.
		if w0 < 0.001 and w1 < 0.001:
			prev = ring
			continue
		var uv_l0 := Vector2(t0, 0.0)
		var uv_m0 := Vector2(t0, 0.5)
		var uv_r0 := Vector2(t0, 1.0)
		var uv_l1 := Vector2(t1, 0.0)
		var uv_m1 := Vector2(t1, 0.5)
		var uv_r1 := Vector2(t1, 1.0)
		if si == segments - 1:
			# Pointed tip: both halves collapse onto the midrib end point.
			_add_tri(st, prev[0], prev[1], ring[1], uv_l0, uv_m0, uv_m1)
			_add_tri(st, prev[1], prev[2], ring[1], uv_m0, uv_r0, uv_m1)
		elif w0 < 0.001:
			# Zero-width collar: fan out from the base point.
			_add_tri(st, prev[1], ring[1], ring[0], uv_m0, uv_m1, uv_l1)
			_add_tri(st, prev[1], ring[2], ring[1], uv_m0, uv_r1, uv_m1)
		else:
			_add_tri(st, prev[0], prev[1], ring[1], uv_l0, uv_m0, uv_m1)
			_add_tri(st, prev[0], ring[1], ring[0], uv_l0, uv_m1, uv_l1)
			_add_tri(st, prev[1], prev[2], ring[2], uv_m0, uv_r0, uv_r1)
			_add_tri(st, prev[1], ring[2], ring[1], uv_m0, uv_r1, uv_m1)
		prev = ring
	st.generate_normals()
	return st.commit()


static func _blade_profile(t: float, shape: LeafShape) -> float:
	## Half-width multiplier (0..1) along the blade. A small floor keeps
	## interior rings from degenerating; the tip itself is closed separately.
	if shape == null or shape.peak < 0.0:
		return maxf(4.0 * t * (1.0 - t), 0.02)
	var peak: float = clampf(shape.peak, 0.05, 0.95)
	if t < peak:
		return lerpf(shape.base_frac, 1.0, sin(t / peak * PI * 0.5))
	# Beyond the widest point the blade narrows slowly, then quickly into an
	# acuminate tip.
	var u: float = (t - peak) / (1.0 - peak)
	return maxf(pow(1.0 - pow(u, 2.2), 0.8), 0.02)


static func _leaf_ring(
	t: float, length: float, width: float, bw: float, rise: float, droop: float, shape: LeafShape
) -> Array[Vector3]:
	## Left edge, midrib and right edge vertex of the blade cross-section at t.
	var half_w: float = width * 0.5 * _blade_profile(t, shape)
	half_w = maxf(half_w, maxf(1.0 - t * 3.0, 0.0) * bw)
	var mid := Vector3(0.0, rise * 4.0 * t * (1.0 - t) - droop * length * t * t * t, length * t)
	var left := Vector2(-half_w, 0.0)
	var right := Vector2(half_w, 0.0)
	if shape != null:
		mid.x += shape.sway * length * t * t
		var lift: float = shape.keel * half_w * (1.0 - t)
		left = Vector2(-half_w, lift).rotated(shape.twist * t)
		right = Vector2(half_w, lift).rotated(shape.twist * t)
	return [mid + Vector3(left.x, left.y, 0.0), mid, mid + Vector3(right.x, right.y, 0.0)]


static func _add_tri(
	st: SurfaceTool,
	a: Vector3,
	b: Vector3,
	c: Vector3,
	uv_a: Vector2,
	uv_b: Vector2,
	uv_c: Vector2,
) -> void:
	st.set_uv(uv_a)
	st.add_vertex(a)
	st.set_uv(uv_b)
	st.add_vertex(b)
	st.set_uv(uv_c)
	st.add_vertex(c)
