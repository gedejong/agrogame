extends RefCounted
## Base class for 3D procedural crop renderers.
## Provides shared utilities: leaf quad builder, stem builder,
## material cache, hash-based randomness, and growth-to-color mapping.

const LEAF_SHADER = preload("res://shaders/crop_leaf.gdshader")

const LEAF_MASKS := {
	"maize": preload("res://assets/textures/leaf_maize_alpha.png"),
	"wheat": preload("res://assets/textures/leaf_wheat_alpha.png"),
	"sorghum": preload("res://assets/textures/leaf_sorghum_alpha.png"),
	"rice": preload("res://assets/textures/leaf_rice_alpha.png"),
	"grape": preload("res://assets/textures/leaf_grape_alpha.png"),
}

const STEM_COLOR := Color(0.55, 0.65, 0.35)
const STEM_SENESCENT := Color(0.65, 0.55, 0.3)
const GRAIN_COLOR := Color(0.85, 0.75, 0.35)


static func hash_val(seed_val: int, idx: int) -> float:
	## Deterministic pseudo-random float in [0, 1).
	var h := (seed_val * 2654435761 + idx * 40503) & 0x7FFFFFFF
	return float(h % 1000) / 1000.0


static func create_leaf_material(
	crop_key: String, senescence: float, stress: float
) -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = LEAF_SHADER
	var mask: Texture2D = LEAF_MASKS.get(crop_key, LEAF_MASKS["maize"])
	mat.set_shader_parameter("alpha_mask", mask)
	mat.set_shader_parameter("senescence", senescence)
	mat.set_shader_parameter("stress", stress)
	return mat


static func create_stem_mesh(
	height: float, radius_bottom: float, radius_top: float
) -> CylinderMesh:
	var cyl := CylinderMesh.new()
	cyl.height = height
	cyl.bottom_radius = radius_bottom
	cyl.top_radius = radius_top
	cyl.radial_segments = 6
	cyl.rings = 1
	return cyl


static func create_stem_material(senescence: float) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = STEM_COLOR.lerp(STEM_SENESCENT, senescence)
	mat.roughness = 0.8
	return mat


static func create_grain_material(grain_frac: float) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = GRAIN_COLOR.darkened((1.0 - grain_frac) * 0.3)
	mat.roughness = 0.7
	return mat


static func create_leaf_quad(
	width: float, length: float, pos: Vector3, rot: Vector3
) -> MeshInstance3D:
	## Create a flat quad mesh for a single leaf.
	var quad := QuadMesh.new()
	quad.size = Vector2(width, length)
	var inst := MeshInstance3D.new()
	inst.mesh = quad
	inst.position = pos
	inst.rotation = rot
	inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	return inst
