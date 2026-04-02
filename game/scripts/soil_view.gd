extends Node2D
## Inline 2D soil cross-section rendered below a selected tile (#114).
## Shows soil layers, water fill, nutrient bars, and SOM bands directly
## in the isometric farm view — no separate screen.

signal closed

## Layer colors by soil texture class (ADR-005)
const LAYER_COLORS := {
	"sand": Color(0.85, 0.78, 0.62),
	"sandy_loam": Color(0.78, 0.70, 0.55),
	"loam": Color(0.60, 0.50, 0.38),
	"clay_loam": Color(0.50, 0.42, 0.32),
	"clay": Color(0.40, 0.32, 0.25),
	"peat": Color(0.25, 0.20, 0.15),
}
const DEFAULT_LAYER_COLOR := Color(0.55, 0.45, 0.35)

## Display dimensions (pixels)
const CUTAWAY_WIDTH := 56
const LAYER_SCALE := 1.5
const BAR_WIDTH := 4

## Overlay colors
const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.5)
const N_COLOR := Color(0.2, 0.75, 0.2, 0.7)
const P_COLOR := Color(0.6, 0.2, 0.75, 0.7)
const SOM_COLOR := Color(0.2, 0.15, 0.05, 0.6)

var _active := false


func show_at(tile_pos: Vector2, soil_state: Dictionary, profile_layers: Array) -> void:
	_clear()
	position = tile_pos + Vector2(0, 8)
	_build_cutaway(soil_state, profile_layers)
	visible = true
	_active = true


func hide_view() -> void:
	visible = false
	_active = false
	closed.emit()


func is_active() -> bool:
	return _active


func _clear() -> void:
	for child in get_children():
		child.queue_free()


func _build_cutaway(soil_state: Dictionary, profile_layers: Array) -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var labile: Array = soil_state.get("som_labile_c", [])
	var stable: Array = soil_state.get("som_stable_c", [])

	var y_off := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var h: float = depth_cm * LAYER_SCALE
		var texture: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.45)

		# Soil layer background
		var layer_rect := ColorRect.new()
		layer_rect.color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)
		layer_rect.size = Vector2(CUTAWAY_WIDTH, h)
		layer_rect.position = Vector2(-CUTAWAY_WIDTH / 2.0, y_off)
		add_child(layer_rect)

		# Water fill from bottom of layer
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill: float = clampf(theta / sat, 0.0, 1.0) if sat > 0 else 0.0
		if fill > 0.01:
			var water_h: float = h * fill
			var water_rect := ColorRect.new()
			water_rect.color = WATER_COLOR
			water_rect.size = Vector2(CUTAWAY_WIDTH - 2, water_h)
			water_rect.position = Vector2(-CUTAWAY_WIDTH / 2.0 + 1, y_off + h - water_h)
			add_child(water_rect)

		# N bar (left edge)
		var no3: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var n_h: float = clampf(no3 / 5.0, 1.0, h * 0.9)
		var n_rect := ColorRect.new()
		n_rect.color = N_COLOR
		n_rect.size = Vector2(BAR_WIDTH, n_h)
		n_rect.position = Vector2(-CUTAWAY_WIDTH / 2.0 - BAR_WIDTH - 2, y_off)
		add_child(n_rect)

		# P bar (right edge)
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var p_h: float = clampf(p_val / 5.0, 1.0, h * 0.9)
		var p_rect := ColorRect.new()
		p_rect.color = P_COLOR
		p_rect.size = Vector2(BAR_WIDTH, p_h)
		p_rect.position = Vector2(CUTAWAY_WIDTH / 2.0 + 2, y_off)
		add_child(p_rect)

		# SOM band (dark strip at top of layer)
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0
		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 0.8)
		if som_frac > 0.02:
			var som_w: float = CUTAWAY_WIDTH * som_frac
			var som_rect := ColorRect.new()
			som_rect.color = SOM_COLOR
			som_rect.size = Vector2(som_w, 4)
			som_rect.position = Vector2(-som_w / 2.0, y_off + 1)
			add_child(som_rect)

		# Layer border
		var border := ColorRect.new()
		border.color = Color(0, 0, 0, 0.3)
		border.size = Vector2(CUTAWAY_WIDTH, 1)
		border.position = Vector2(-CUTAWAY_WIDTH / 2.0, y_off + h - 1)
		add_child(border)

		y_off += h
