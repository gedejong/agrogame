extends RefCounted
## Billboard crop sprites for 3D world (Phase 2, ADR-007).
## Creates Sprite3D per plant with alpha scissor, shadow, and billboard mode.

const CropRenderer = preload("res://scripts/crop_renderer.gd")

const PLANTS_H := 4
const PLANTS_V := 4
const PIXEL_SIZE_BASE := 0.012
const Y_OFFSET := 0.01

const STAGE_SUFFIX := {
	0: "",
	1: "seedling",
	2: "vegetative",
	3: "flowering",
	4: "mature",
}

const STRESS_WILTING := 1
const STRESS_N_DEFICIENT := 2


static func create_plants(tile_size: float, col: int, row: int) -> Array[Sprite3D]:
	var sprites: Array[Sprite3D] = []
	for hi in range(PLANTS_H):
		var u: float = (float(hi) + 0.5) / float(PLANTS_H)
		for vi in range(PLANTS_V):
			var v: float = (float(vi) + 0.5) / float(PLANTS_V)
			var lx: float = (u - 0.5) * tile_size
			var lz: float = (v - 0.5) * tile_size
			var seed_val := col * 7 + row * 13 + hi * 3 + vi * 5
			var cell_w: float = tile_size / float(PLANTS_H)
			var jitter_max: float = cell_w * 0.08
			var jx: float = (fmod(float(seed_val % 7), 3.0) - 1.5) * jitter_max
			var jz: float = (fmod(float((seed_val * 3) % 5), 2.0) - 1.0) * jitter_max
			var spr := Sprite3D.new()
			spr.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			spr.pixel_size = PIXEL_SIZE_BASE
			spr.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			spr.alpha_scissor_threshold = 0.1
			spr.transparent = true
			spr.shaded = true
			spr.position = Vector3(lx + jx, Y_OFFSET, lz + jz)
			spr.visible = false
			sprites.append(spr)
	return sprites


static func update_sprite(
	spr: Sprite3D,
	crop_key: String,
	stage: int,
	lai: float,
	stress: int,
) -> void:
	var suffix: String = STAGE_SUFFIX.get(stage, "")
	if suffix.is_empty():
		spr.visible = false
		return

	var path := CropRenderer.crop_sprite_path(crop_key, suffix)
	var tex: Texture2D = load(path) if ResourceLoader.exists(path) else null
	if not tex:
		spr.visible = false
		return

	spr.texture = tex
	# Shift sprite up so stem base (bottom of texture) sits at ground.
	# Sprite3D offset is in pixel coords (+Y = down). Move up = negative Y.
	spr.offset = Vector2(0.0, -tex.get_height() * 0.5)
	# LAI-based scaling: seedling small, mature large
	var lai_frac: float = clampf(lai / 6.0, 0.0, 1.0)
	var scale_factor: float = clampf(0.3 + lai_frac * 0.7, 0.3, 1.0)
	spr.pixel_size = PIXEL_SIZE_BASE * scale_factor

	var color := Color.WHITE
	if stress == STRESS_WILTING:
		color = Color(0.8, 0.7, 0.5)
	elif stress == STRESS_N_DEFICIENT:
		color = Color(0.85, 0.9, 0.6)
	spr.modulate = color
	spr.visible = true
