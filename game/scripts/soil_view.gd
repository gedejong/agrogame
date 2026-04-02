extends Node2D
## 2.5D isometric soil cutaway — excavation pit style (#114).
## Spans a 2×2 tile area. Dark shadow pit behind exposed layer faces.
## Labels on the faces. Water fill visible per layer.

signal closed

## Layer colors by soil texture class (ADR-005)
const LAYER_COLORS := {
	"sand": Color(0.82, 0.75, 0.60),
	"sandy_loam": Color(0.75, 0.67, 0.52),
	"loam": Color(0.58, 0.48, 0.36),
	"clay_loam": Color(0.48, 0.40, 0.30),
	"clay": Color(0.42, 0.34, 0.26),
	"peat": Color(0.25, 0.20, 0.15),
}
const DEFAULT_LAYER_COLOR := Color(0.55, 0.45, 0.35)

## Isometric tile half-dimensions
const HALF_W := 32.0
const HALF_H := 16.0

## Scale: bigger cutaway (2 tiles wide)
const SCALE_X := 2.0
const SCALE_Y := 2.0

## Vertical scale: cm to pixels
const DEPTH_SCALE := 0.6

## Colors
const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.45)
const N_COLOR := Color(0.2, 0.75, 0.2, 0.7)
const P_COLOR := Color(0.6, 0.2, 0.75, 0.7)
const SOM_COLOR := Color(0.7, 0.5, 0.2, 0.7)
const PIT_SHADOW_COLOR := Color(0.05, 0.03, 0.02, 0.75)
const ROOT_COLOR := Color(0.55, 0.40, 0.20)
## Root depth by crop stage (fraction of total depth).
const ROOT_DEPTH_BY_STAGE := {
	"planted": 0.0,
	"emerged": 0.1,
	"vegetative": 0.4,
	"flowering": 0.7,
	"grain_fill": 0.85,
	"maturity": 0.9,
}

var _active := false
var _hw: float = HALF_W * SCALE_X
var _hh: float = HALF_H * SCALE_Y


func show_at(
	tile_pos: Vector2,
	soil_state: Dictionary,
	profile_layers: Array,
	crop_stage: String = "",
) -> void:
	_clear()
	position = tile_pos
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


func _build_cutaway(soil_state: Dictionary, profile_layers: Array, crop_stage: String = "") -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var labile: Array = soil_state.get("som_labile_c", [])
	var stable: Array = soil_state.get("som_stable_c", [])

	# Total depth for pit shadow
	var total_h := 0.0
	for ld: Dictionary in profile_layers:
		total_h += ld.get("depth_cm", 20.0) * DEPTH_SCALE

	# Dark pit shadow behind everything — the "hole" in the ground
	_build_pit_shadow(total_h)

	# Layer faces
	var y_off := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var h: float = depth_cm * DEPTH_SCALE
		var texture: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.45)
		var base_color: Color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)

		# Left face (slightly darker — shadow side)
		var lf := Polygon2D.new()
		lf.polygon = PackedVector2Array(
			[
				Vector2(-_hw, y_off),
				Vector2(0, _hh + y_off),
				Vector2(0, _hh + y_off + h),
				Vector2(-_hw, y_off + h),
			]
		)
		lf.color = base_color.darkened(0.2)
		add_child(lf)

		# Right face (lit side)
		var rf := Polygon2D.new()
		rf.polygon = PackedVector2Array(
			[
				Vector2(0, _hh + y_off),
				Vector2(_hw, y_off),
				Vector2(_hw, y_off + h),
				Vector2(0, _hh + y_off + h),
			]
		)
		rf.color = base_color
		add_child(rf)

		# Water fill on both faces
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill: float = clampf(theta / sat, 0.0, 1.0) if sat > 0 else 0.0
		if fill > 0.02:
			var wh: float = h * fill
			var wb := y_off + h
			var wt := wb - wh
			var wl := Polygon2D.new()
			wl.polygon = PackedVector2Array(
				[
					Vector2(-_hw, wt),
					Vector2(0, _hh + wt),
					Vector2(0, _hh + wb),
					Vector2(-_hw, wb),
				]
			)
			wl.color = WATER_COLOR
			add_child(wl)
			var wr := Polygon2D.new()
			wr.polygon = PackedVector2Array(
				[
					Vector2(0, _hh + wt),
					Vector2(_hw, wt),
					Vector2(_hw, wb),
					Vector2(0, _hh + wb),
				]
			)
			wr.color = WATER_COLOR
			add_child(wr)

		# Layer label on right face
		var label := Label.new()
		label.text = "%s (%dcm)" % [texture, int(depth_cm)]
		label.add_theme_font_size_override("font_size", 8)
		label.add_theme_color_override("font_color", Color(0.95, 0.92, 0.85))
		label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.8))
		label.position = Vector2(_hw * 0.1, y_off + h * 0.3)
		add_child(label)

		# Divider line
		var edge := Line2D.new()
		edge.points = PackedVector2Array(
			[
				Vector2(-_hw, y_off + h),
				Vector2(0, _hh + y_off + h),
				Vector2(_hw, y_off + h),
			]
		)
		edge.width = 0.5
		edge.default_color = Color(0, 0, 0, 0.3)
		add_child(edge)

		y_off += h

	# Surface rim — bright edge where cut meets ground
	var rim := Line2D.new()
	rim.points = PackedVector2Array(
		[
			Vector2(-_hw, 0),
			Vector2(0, _hh),
			Vector2(_hw, 0),
		]
	)
	rim.width = 2.5
	rim.default_color = Color(0.85, 0.78, 0.65, 0.7)
	add_child(rim)

	# Outer edge
	var outline := Line2D.new()
	outline.points = PackedVector2Array(
		[
			Vector2(-_hw, 0),
			Vector2(-_hw, y_off),
			Vector2(0, _hh + y_off),
			Vector2(_hw, y_off),
			Vector2(_hw, 0),
		]
	)
	outline.width = 2.0
	outline.default_color = Color(0, 0, 0, 0.7)
	add_child(outline)

	# Info boxes with N/P/SOM bars
	_build_info_boxes(profile_layers, thetas, no3_arr, p_arr, labile, stable, y_off)

	# Roots
	_build_roots(profile_layers, crop_stage)


func _build_pit_shadow(total_h: float) -> void:
	## Dark shadow behind the cutaway — the "hole" visible around the edges.
	## Slightly larger than the cutaway to create a shadow border.
	var pad := 4.0
	var shadow := Polygon2D.new()
	shadow.polygon = PackedVector2Array(
		[
			Vector2(-_hw - pad, -pad),
			Vector2(0, _hh - pad),
			Vector2(_hw + pad, -pad),
			Vector2(_hw + pad, total_h + pad),
			Vector2(0, _hh + total_h + pad),
			Vector2(-_hw - pad, total_h + pad),
		]
	)
	shadow.color = PIT_SHADOW_COLOR
	add_child(shadow)

	# Gradient shadow at the top — darker near surface
	var grad_h: float = minf(total_h * 0.3, 15.0)
	var grad_l := Polygon2D.new()
	grad_l.polygon = PackedVector2Array(
		[
			Vector2(-_hw, 0),
			Vector2(0, _hh),
			Vector2(0, _hh + grad_h),
			Vector2(-_hw, grad_h),
		]
	)
	grad_l.color = Color(0, 0, 0, 0.3)
	add_child(grad_l)
	var grad_r := Polygon2D.new()
	grad_r.polygon = PackedVector2Array(
		[
			Vector2(0, _hh),
			Vector2(_hw, 0),
			Vector2(_hw, grad_h),
			Vector2(0, _hh + grad_h),
		]
	)
	grad_r.color = Color(0, 0, 0, 0.2)
	add_child(grad_r)


func _build_info_boxes(
	profile_layers: Array,
	_thetas: Array,
	no3_arr: Array,
	p_arr: Array,
	labile: Array,
	stable: Array,
	_total_y: float,
) -> void:
	var box_x := _hw + 16
	var box_w := 65
	var box_h := 24
	var box_gap := 3
	var bar_max_w := 28
	var y_off := 0.0
	var next_box_y := 0.0

	for i in range(profile_layers.size()):
		var h: float = profile_layers[i].get("depth_cm", 20.0) * DEPTH_SCALE
		var sat: float = profile_layers[i].get("saturation", 0.45)
		var layer_mid_y: float = y_off + h / 2.0
		var ideal_y: float = layer_mid_y - box_h / 2.0
		var box_y: float = maxf(ideal_y, next_box_y)
		var box_mid_y: float = box_y + box_h / 2.0
		next_box_y = box_y + box_h + box_gap

		var line := Line2D.new()
		line.points = PackedVector2Array(
			[
				Vector2(_hw, layer_mid_y),
				Vector2(box_x, box_mid_y),
			]
		)
		line.width = 1.0
		line.default_color = Color(0.5, 0.5, 0.5, 0.5)
		add_child(line)

		var bg := Polygon2D.new()
		bg.polygon = PackedVector2Array(
			[
				Vector2(box_x, box_y),
				Vector2(box_x + box_w, box_y),
				Vector2(box_x + box_w, box_y + box_h),
				Vector2(box_x, box_y + box_h),
			]
		)
		bg.color = Color(0.08, 0.08, 0.08, 0.9)
		add_child(bg)

		var no3: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0

		var n_frac: float = clampf(no3 / 5.0, 0.0, 1.0)
		_add_bar(box_x + 2, box_y + 2, bar_max_w, 5, n_frac, N_COLOR)

		var p_frac: float = clampf(p_val / 5.0, 0.0, 1.0)
		_add_bar(box_x + 2, box_y + 9, bar_max_w, 5, p_frac, P_COLOR)

		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 1.0)
		_add_bar(box_x + 2, box_y + 16, bar_max_w, 5, som_frac, SOM_COLOR)

		var lx: float = box_x + bar_max_w + 4
		_add_tiny_label(lx, box_y + 1, "N", N_COLOR)
		_add_tiny_label(lx, box_y + 8, "P", P_COLOR)
		_add_tiny_label(lx, box_y + 15, "S", SOM_COLOR)

		y_off += h


func _add_bar(x: float, y: float, max_w: float, h: float, frac: float, color: Color) -> void:
	var track := Polygon2D.new()
	track.polygon = PackedVector2Array(
		[
			Vector2(x, y),
			Vector2(x + max_w, y),
			Vector2(x + max_w, y + h),
			Vector2(x, y + h),
		]
	)
	track.color = Color(0.2, 0.2, 0.2, 0.5)
	add_child(track)
	if frac > 0.01:
		var fill := Polygon2D.new()
		var fw: float = max_w * frac
		fill.polygon = PackedVector2Array(
			[
				Vector2(x, y),
				Vector2(x + fw, y),
				Vector2(x + fw, y + h),
				Vector2(x, y + h),
			]
		)
		fill.color = color
		add_child(fill)


func _add_tiny_label(x: float, y: float, text: String, color: Color) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 7)
	label.add_theme_color_override("font_color", color)
	label.position = Vector2(x, y)
	add_child(label)


func _build_roots(profile_layers: Array, crop_stage: String = "") -> void:
	var depth_frac: float = ROOT_DEPTH_BY_STAGE.get(crop_stage, 0.0)
	if depth_frac < 0.01:
		return
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 20.0) * DEPTH_SCALE
	if total_depth <= 0:
		return
	var root_depth: float = total_depth * depth_frac
	var root_start := Vector2(0, _hh + 2)
	var root_end := Vector2(0, _hh + root_depth)
	var taproot := Line2D.new()
	taproot.points = PackedVector2Array([root_start, root_end])
	taproot.width = clampf(depth_frac * 3.0, 0.5, 2.5)
	taproot.default_color = ROOT_COLOR
	add_child(taproot)
	var branch_fracs := [0.1, 0.2, 0.35, 0.5, 0.65]
	for bf: float in branch_fracs:
		if bf > depth_frac:
			break
		var y: float = _hh + total_depth * bf
		var density: float = (depth_frac - bf) / depth_frac
		var spread: float = _hw * 0.3 * density
		var width: float = 1.5 * density
		if width < 0.3 or spread < 2.0:
			continue
		var left := Line2D.new()
		left.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(-spread * 0.6, y - spread * 0.1),
			]
		)
		left.width = width
		left.default_color = ROOT_COLOR
		add_child(left)
		var right := Line2D.new()
		right.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(spread * 0.6, y - spread * 0.1),
			]
		)
		right.width = width
		right.default_color = ROOT_COLOR
		add_child(right)
