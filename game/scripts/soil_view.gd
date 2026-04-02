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

## Vertical scale: cm to pixels for layer depth (compact to fit under tile)
const DEPTH_SCALE := 0.4

## Overlay colors
const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.45)
const N_COLOR := Color(0.2, 0.75, 0.2, 0.7)
const P_COLOR := Color(0.6, 0.2, 0.75, 0.7)
const SOM_COLOR := Color(0.2, 0.15, 0.05, 0.5)
const WALL_DARKEN := 0.7
const ROOT_COLOR := Color(0.55, 0.40, 0.20)
## Root depth fraction by crop stage (fraction of total soil depth).
## Source: approximate DSSAT/APSIM root growth curves for maize.
const ROOT_DEPTH_BY_STAGE := {
	"planted": 0.0,
	"emerged": 0.1,
	"vegetative": 0.4,
	"flowering": 0.7,
	"grain_fill": 0.85,
	"maturity": 0.9,
}

var _active := false


func show_at(
	tile_pos: Vector2,
	soil_state: Dictionary,
	profile_layers: Array,
	crop_stage: String = "",
) -> void:
	_clear()
	position = tile_pos
	modulate.a = 0.85
	_build_cutaway(soil_state, profile_layers, crop_stage)
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


func _build_cutaway(soil_state: Dictionary, profile_layers: Array, crop_stage: String = "") -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var labile: Array = soil_state.get("som_labile_c", [])
	var stable: Array = soil_state.get("som_stable_c", [])

	# Wall offset gives the 2.5D depth look
	var wall_w := HALF_W * 0.3
	var y_top := HALF_H
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var h: float = depth_cm * DEPTH_SCALE
		var texture: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.45)
		var base_color: Color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)
		var y_bot := y_top + h

		# Front face — simple rectangle inset from tile edges
		var front := Polygon2D.new()
		front.polygon = PackedVector2Array(
			[
				Vector2(-HALF_W + 2, y_top),
				Vector2(HALF_W - wall_w, y_top),
				Vector2(HALF_W - wall_w, y_bot),
				Vector2(-HALF_W + 2, y_bot),
			]
		)
		front.color = base_color
		add_child(front)

		# Right wall (darker, gives depth)
		var rw := Polygon2D.new()
		rw.polygon = PackedVector2Array(
			[
				Vector2(HALF_W - wall_w, y_top),
				Vector2(HALF_W, y_top - 3),
				Vector2(HALF_W, y_bot - 3),
				Vector2(HALF_W - wall_w, y_bot),
			]
		)
		rw.color = base_color.darkened(0.3)
		add_child(rw)

		# Water fill (blue band at bottom of layer)
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill: float = clampf(theta / sat, 0.0, 1.0) if sat > 0 else 0.0
		if fill > 0.02:
			var water_h: float = h * fill
			var wy := y_bot - water_h
			var water := Polygon2D.new()
			water.polygon = PackedVector2Array(
				[
					Vector2(-HALF_W + 3, wy),
					Vector2(HALF_W - wall_w - 1, wy),
					Vector2(HALF_W - wall_w - 1, y_bot - 1),
					Vector2(-HALF_W + 3, y_bot - 1),
				]
			)
			water.color = WATER_COLOR
			add_child(water)

		# SOM band (dark strip at top of layer, width = SOM fraction)
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0
		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 0.8)
		if som_frac > 0.02:
			var face_w: float = HALF_W * 2 - wall_w - 4
			var som_w: float = face_w * som_frac
			var som := Polygon2D.new()
			som.polygon = PackedVector2Array(
				[
					Vector2(-HALF_W + 3, y_top),
					Vector2(-HALF_W + 3 + som_w, y_top),
					Vector2(-HALF_W + 3 + som_w, y_top + 3),
					Vector2(-HALF_W + 3, y_top + 3),
				]
			)
			som.color = SOM_COLOR
			add_child(som)

		# Thin divider line between layers
		var divider := Line2D.new()
		divider.points = PackedVector2Array(
			[
				Vector2(-HALF_W + 2, y_bot),
				Vector2(HALF_W, y_bot - 3),
			]
		)
		divider.width = 0.5
		divider.default_color = Color(0, 0, 0, 0.25)
		add_child(divider)

		y_top = y_bot

	# N and P indicator dots (beside each layer)
	_build_nutrient_bars(profile_layers, no3_arr, p_arr)

	# Root structure (depth tied to crop stage)
	_build_roots(profile_layers, crop_stage)


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


func _build_roots(profile_layers: Array, crop_stage: String = "") -> void:
	## Draw roots proportional to crop stage — no roots before emergence.
	var depth_frac: float = ROOT_DEPTH_BY_STAGE.get(crop_stage, 0.0)
	if depth_frac < 0.01:
		return

	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 20.0) * DEPTH_SCALE
	if total_depth <= 0:
		return

	var root_depth: float = total_depth * depth_frac

	# Main taproot
	var root_start := Vector2(0, HALF_H + 2)
	var root_end := Vector2(0, HALF_H + root_depth)
	var taproot := Line2D.new()
	taproot.points = PackedVector2Array([root_start, root_end])
	taproot.width = clampf(depth_frac * 3.0, 0.5, 2.5)
	taproot.default_color = ROOT_COLOR
	add_child(taproot)

	# Lateral branches — only where roots have reached
	var branch_fracs := [0.1, 0.2, 0.35, 0.5, 0.65]
	for bf: float in branch_fracs:
		if bf > depth_frac:
			break
		var y: float = HALF_H + total_depth * bf
		var density: float = (depth_frac - bf) / depth_frac
		var spread: float = HALF_W * 0.5 * density
		var width: float = 1.5 * density
		if width < 0.3 or spread < 2.0:
			continue
		var left := Line2D.new()
		left.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(-spread * 0.5, y + 3),
				Vector2(-spread, y + 5),
			]
		)
		left.width = width
		left.default_color = ROOT_COLOR
		add_child(left)
		var right := Line2D.new()
		right.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(spread * 0.4, y + 4),
				Vector2(spread * 0.7, y + 6),
			]
		)
		right.width = width
		right.default_color = ROOT_COLOR
		add_child(right)
