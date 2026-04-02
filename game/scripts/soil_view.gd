extends Node2D
## Inline 2.5D isometric soil cutaway rendered below a selected tile (#114).
## Diamond-shaped layers match tile geometry with side walls for depth.
## Semi-transparent so the farm view remains visible behind.

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

## Isometric tile half-dimensions (must match TileMapLayer tile size)
const HALF_W := 32.0
const HALF_H := 16.0

## Vertical scale: cm to pixels for layer depth
const DEPTH_SCALE := 1.2

## Overlay colors
const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.45)
const N_COLOR := Color(0.2, 0.75, 0.2, 0.7)
const P_COLOR := Color(0.6, 0.2, 0.75, 0.7)
const SOM_COLOR := Color(0.2, 0.15, 0.05, 0.5)
const WALL_DARKEN := 0.7
const ROOT_COLOR := Color(0.55, 0.40, 0.20)

var _active := false


func show_at(tile_pos: Vector2, soil_state: Dictionary, profile_layers: Array) -> void:
	_clear()
	position = tile_pos
	modulate.a = 0.85
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


func _diamond_top(y: float) -> PackedVector2Array:
	## Returns the 4 points of an isometric diamond at vertical offset y.
	return PackedVector2Array(
		[
			Vector2(0, y - HALF_H),
			Vector2(HALF_W, y),
			Vector2(0, y + HALF_H),
			Vector2(-HALF_W, y),
		]
	)


func _build_cutaway(soil_state: Dictionary, profile_layers: Array) -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var labile: Array = soil_state.get("som_labile_c", [])
	var stable: Array = soil_state.get("som_stable_c", [])

	var y_top := HALF_H
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var h: float = depth_cm * DEPTH_SCALE
		var texture: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.45)
		var base_color: Color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)
		var y_bot := y_top + h

		# Front face (isometric diamond stretched vertically)
		var front := Polygon2D.new()
		front.polygon = PackedVector2Array(
			[
				Vector2(0, y_top - HALF_H),
				Vector2(HALF_W, y_top),
				Vector2(HALF_W, y_bot),
				Vector2(0, y_bot + HALF_H),
				Vector2(-HALF_W, y_bot),
				Vector2(-HALF_W, y_top),
			]
		)
		front.color = base_color
		add_child(front)

		# Right wall (darker for depth)
		var right_wall := Polygon2D.new()
		right_wall.polygon = PackedVector2Array(
			[
				Vector2(HALF_W, y_top),
				Vector2(HALF_W, y_bot),
				Vector2(0, y_bot + HALF_H),
				Vector2(0, y_top + HALF_H),
			]
		)
		right_wall.color = base_color.darkened(1.0 - WALL_DARKEN)
		add_child(right_wall)

		# Left wall (slightly darker)
		var left_wall := Polygon2D.new()
		left_wall.polygon = PackedVector2Array(
			[
				Vector2(-HALF_W, y_top),
				Vector2(0, y_top + HALF_H),
				Vector2(0, y_bot + HALF_H),
				Vector2(-HALF_W, y_bot),
			]
		)
		left_wall.color = base_color.darkened(1.0 - WALL_DARKEN * 0.85)
		add_child(left_wall)

		# Water fill (blue band at bottom of layer)
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill: float = clampf(theta / sat, 0.0, 1.0) if sat > 0 else 0.0
		if fill > 0.02:
			var water_h: float = h * fill
			var wy := y_bot - water_h
			var water := Polygon2D.new()
			water.polygon = PackedVector2Array(
				[
					Vector2(0, wy - HALF_H * 0.9),
					Vector2(HALF_W * 0.9, wy),
					Vector2(HALF_W * 0.9, y_bot),
					Vector2(0, y_bot + HALF_H * 0.9),
					Vector2(-HALF_W * 0.9, y_bot),
					Vector2(-HALF_W * 0.9, wy),
				]
			)
			water.color = WATER_COLOR
			add_child(water)

		# SOM band at top of each layer
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0
		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 0.8)
		if som_frac > 0.02:
			var som_h: float = 3.0 + som_frac * 5.0
			var som := Polygon2D.new()
			var sw: float = HALF_W * som_frac * 1.2
			var sh: float = HALF_H * som_frac * 1.2
			som.polygon = PackedVector2Array(
				[
					Vector2(0, y_top - sh),
					Vector2(sw, y_top),
					Vector2(sw, y_top + som_h),
					Vector2(0, y_top + som_h + sh),
					Vector2(-sw, y_top + som_h),
					Vector2(-sw, y_top),
				]
			)
			som.color = SOM_COLOR
			add_child(som)

		# Layer divider line
		var divider := Line2D.new()
		divider.points = PackedVector2Array(
			[
				Vector2(-HALF_W, y_bot),
				Vector2(0, y_bot + HALF_H),
				Vector2(HALF_W, y_bot),
			]
		)
		divider.width = 1.0
		divider.default_color = Color(0, 0, 0, 0.3)
		add_child(divider)

		y_top = y_bot

	# N and P indicator bars (side labels)
	_build_nutrient_bars(profile_layers, no3_arr, p_arr)

	# Root structure
	_build_roots(profile_layers)

	# Bottom cap (diamond at bottom)
	var bottom := Polygon2D.new()
	bottom.polygon = _diamond_top(y_top + HALF_H)
	var last_tex: String = profile_layers[-1].get("texture", "loam") if profile_layers else "loam"
	bottom.color = LAYER_COLORS.get(last_tex, DEFAULT_LAYER_COLOR).darkened(0.3)
	add_child(bottom)


func _build_nutrient_bars(profile_layers: Array, no3_arr: Array, p_arr: Array) -> void:
	var y_off := HALF_H
	for i in range(profile_layers.size()):
		var depth_cm: float = profile_layers[i].get("depth_cm", 20.0)
		var h: float = depth_cm * DEPTH_SCALE
		var mid_y: float = y_off + h / 2.0

		# N dot (left)
		var no3: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var n_r: float = clampf(no3 / 3.0, 2.0, 8.0)
		var n_dot := Polygon2D.new()
		n_dot.polygon = _circle_points(Vector2(-HALF_W - 12, mid_y), n_r)
		n_dot.color = N_COLOR
		add_child(n_dot)

		# P dot (right)
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var p_r: float = clampf(p_val / 3.0, 2.0, 8.0)
		var p_dot := Polygon2D.new()
		p_dot.polygon = _circle_points(Vector2(HALF_W + 12, mid_y), p_r)
		p_dot.color = P_COLOR
		add_child(p_dot)

		y_off += h


func _circle_points(center: Vector2, radius: float) -> PackedVector2Array:
	var pts := PackedVector2Array()
	for j in range(8):
		var angle: float = j * TAU / 8.0
		pts.append(center + Vector2(cos(angle), sin(angle)) * radius)
	return pts


func _build_roots(profile_layers: Array) -> void:
	## Draw branching root structure that thins with depth.
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 20.0) * DEPTH_SCALE
	if total_depth <= 0:
		return

	# Main taproot
	var root_start := Vector2(0, HALF_H + 2)
	var root_end := Vector2(0, HALF_H + total_depth * 0.7)
	var taproot := Line2D.new()
	taproot.points = PackedVector2Array([root_start, root_end])
	taproot.width = 2.5
	taproot.default_color = ROOT_COLOR
	add_child(taproot)

	# Lateral branches at different depths
	var branches := [0.15, 0.25, 0.4, 0.55, 0.7]
	for frac: float in branches:
		var y: float = HALF_H + total_depth * frac
		var spread: float = HALF_W * 0.6 * (1.0 - frac)
		var width: float = 2.0 * (1.0 - frac)
		if width < 0.5:
			continue
		# Left branch
		var left := Line2D.new()
		left.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(-spread * 0.5, y + 3),
				Vector2(-spread, y + 6),
			]
		)
		left.width = width
		left.default_color = ROOT_COLOR
		add_child(left)
		# Right branch
		var right := Line2D.new()
		right.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(spread * 0.4, y + 4),
				Vector2(spread * 0.8, y + 8),
			]
		)
		right.width = width
		right.default_color = ROOT_COLOR
		add_child(right)
