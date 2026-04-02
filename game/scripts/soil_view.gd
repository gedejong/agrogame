extends Node2D
## Inline 2.5D isometric soil cutaway rendered below a selected tile (#114).
## Two visible faces (left + right) extend down from the tile diamond,
## like looking into a hole dug in the isometric ground.

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
const DEPTH_SCALE := 0.35

## Overlay colors
const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.5)
const N_COLOR := Color(0.2, 0.75, 0.2, 0.7)
const P_COLOR := Color(0.6, 0.2, 0.75, 0.7)
const SOM_COLOR := Color(0.7, 0.5, 0.2, 0.7)
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
var _cur_parent: Node2D


func show_at(
	tile_pos: Vector2,
	soil_state: Dictionary,
	profile_layers: Array,
	crop_stage: String = "",
) -> void:
	show_columns(
		[
			{
				"pos": tile_pos,
				"soil_state": soil_state,
				"profile": profile_layers,
				"crop_stage": crop_stage,
				"show_info": true,
			}
		]
	)


func show_columns(columns: Array) -> void:
	_clear()
	position = Vector2.ZERO
	modulate.a = 0.85
	for col_data: Dictionary in columns:
		var pos: Vector2 = col_data.get("pos", Vector2.ZERO)
		var soil_state: Dictionary = col_data.get("soil_state", {})
		var profile: Array = col_data.get("profile", [])
		var stage: String = col_data.get("crop_stage", "")
		var show_info: bool = col_data.get("show_info", false)
		_build_column(pos, soil_state, profile, stage, show_info)
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


func _build_column(
	pos: Vector2,
	soil_state: Dictionary,
	profile_layers: Array,
	crop_stage: String = "",
	show_info: bool = true,
) -> void:
	var container := Node2D.new()
	container.position = pos
	add_child(container)
	_cur_parent = container
	_build_cutaway(soil_state, profile_layers, crop_stage, show_info)


func _add(node: Node) -> void:
	_cur_parent.add_child(node)


func _build_cutaway(
	soil_state: Dictionary,
	profile_layers: Array,
	crop_stage: String = "",
	show_info: bool = true,
) -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var labile: Array = soil_state.get("som_labile_c", [])
	var stable: Array = soil_state.get("som_stable_c", [])

	## Tile diamond vertices (local coords, center = 0,0):
	##   Top:   (0, -HH)
	##   Right: (HW, 0)
	##   Bottom:(0, HH)
	##   Left:  (-HW, 0)
	##
	## The cutaway shows two inner faces of an isometric box below the tile.
	## Left face runs from Left vertex to Bottom vertex, dropping by h.
	## Right face runs from Bottom vertex to Right vertex, dropping by h.

	# Calculate total depth for shadow
	var total_h := 0.0
	for layer_d: Dictionary in profile_layers:
		total_h += layer_d.get("depth_cm", 20.0) * DEPTH_SCALE

	# Shadow inside the pit — dark gradient overlay on both faces
	# Darker at top (near surface), fading toward bottom
	var shadow_h: float = minf(total_h * 0.4, 12.0)
	var shadow_left := Polygon2D.new()
	shadow_left.polygon = PackedVector2Array(
		[
			Vector2(-HALF_W, 0),
			Vector2(0, HALF_H),
			Vector2(0, HALF_H + shadow_h),
			Vector2(-HALF_W, shadow_h),
		]
	)
	shadow_left.color = Color(0, 0, 0, 0.35)
	_add(shadow_left)
	var shadow_right := Polygon2D.new()
	shadow_right.polygon = PackedVector2Array(
		[
			Vector2(0, HALF_H),
			Vector2(HALF_W, 0),
			Vector2(HALF_W, shadow_h),
			Vector2(0, HALF_H + shadow_h),
		]
	)
	shadow_right.color = Color(0, 0, 0, 0.25)
	_add(shadow_right)

	var y_off := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var h: float = depth_cm * DEPTH_SCALE
		var texture: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.45)
		var base_color: Color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)
		# Darken deeper layers to hint at depth
		var depth_darken: float = float(i) * 0.08
		base_color = base_color.darkened(depth_darken)

		# Left face (shadow side)
		var lf := Polygon2D.new()
		lf.polygon = PackedVector2Array(
			[
				Vector2(-HALF_W, y_off),
				Vector2(0, HALF_H + y_off),
				Vector2(0, HALF_H + y_off + h),
				Vector2(-HALF_W, y_off + h),
			]
		)
		lf.color = base_color.darkened(0.15)
		_add(lf)

		# Right face: bottom vertex (0, HH) to right vertex (HW, 0), dropped by y_off
		var rf := Polygon2D.new()
		rf.polygon = PackedVector2Array(
			[
				Vector2(0, HALF_H + y_off),
				Vector2(HALF_W, y_off),
				Vector2(HALF_W, y_off + h),
				Vector2(0, HALF_H + y_off + h),
			]
		)
		rf.color = base_color
		_add(rf)

		# Water fill on BOTH faces (consistent level)
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill: float = clampf(theta / sat, 0.0, 1.0) if sat > 0 else 0.0
		if fill > 0.02:
			var wh: float = h * fill
			var wb := y_off + h
			var wt := wb - wh
			# Water on left face
			var wl := Polygon2D.new()
			wl.polygon = PackedVector2Array(
				[
					Vector2(-HALF_W, wt),
					Vector2(0, HALF_H + wt),
					Vector2(0, HALF_H + wb),
					Vector2(-HALF_W, wb),
				]
			)
			wl.color = WATER_COLOR
			_add(wl)
			# Water on right face
			var wr := Polygon2D.new()
			wr.polygon = PackedVector2Array(
				[
					Vector2(0, HALF_H + wt),
					Vector2(HALF_W, wt),
					Vector2(HALF_W, wb),
					Vector2(0, HALF_H + wb),
				]
			)
			wr.color = WATER_COLOR
			_add(wr)

		# Bottom edge (isometric V-line)
		var edge := Line2D.new()
		edge.points = PackedVector2Array(
			[
				Vector2(-HALF_W, y_off + h),
				Vector2(0, HALF_H + y_off + h),
				Vector2(HALF_W, y_off + h),
			]
		)
		edge.width = 0.5
		edge.default_color = Color(0, 0, 0, 0.3)
		_add(edge)

		y_off += h

	# Single diagonal shadow across the full column height on the right face.
	# Represents shadow cast by the soil above into the pit.
	var shadow := Polygon2D.new()
	shadow.polygon = PackedVector2Array(
		[
			Vector2(HALF_W, 0),
			Vector2(HALF_W, y_off),
			Vector2(0, HALF_H + y_off),
		]
	)
	shadow.color = Color(0, 0, 0, 0.18)
	_add(shadow)

	if show_info:
		# Info boxes on a high-z container so they render above tiles
		var prev_parent := _cur_parent
		var overlay := Node2D.new()
		overlay.position = _cur_parent.position
		overlay.z_index = 200
		add_child(overlay)
		_cur_parent = overlay
		_build_info_boxes_overlay(profile_layers, thetas, no3_arr, p_arr, labile, stable)
		_cur_parent = prev_parent

	# Root structure (depth tied to crop stage)
	_build_roots(profile_layers, crop_stage)


func _build_info_boxes_overlay(
	profile_layers: Array,
	thetas: Array,
	no3_arr: Array,
	p_arr: Array,
	labile: Array,
	stable: Array,
) -> void:
	## Info boxes to the right of the cutaway, one per layer.
	## Boxes are spaced to avoid overlap; diagonal connector when displaced.
	var box_x := HALF_W + 20
	var box_w := 70
	var box_h := 28
	var box_gap := 3
	var bar_max_w := 30
	var y_off := 0.0
	var next_box_y := 0.0  # tracks bottom of last box to prevent overlap

	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var h: float = layer.get("depth_cm", 20.0) * DEPTH_SCALE
		var sat: float = layer.get("saturation", 0.45)
		var layer_mid_y: float = y_off + h / 2.0
		# Ideal position centered on layer, but don't overlap previous box
		var ideal_y: float = layer_mid_y - box_h / 2.0
		var box_y: float = maxf(ideal_y, next_box_y)
		var box_mid_y: float = box_y + box_h / 2.0
		next_box_y = box_y + box_h + box_gap

		# Connector line — diagonal if box is displaced from layer center
		var line := Line2D.new()
		line.points = PackedVector2Array(
			[
				Vector2(HALF_W, layer_mid_y),
				Vector2(box_x, box_mid_y),
			]
		)
		line.width = 1.0
		line.default_color = Color(0.5, 0.5, 0.5, 0.6)
		_add(line)

		# Dark box background
		var bg := Polygon2D.new()
		bg.polygon = PackedVector2Array(
			[
				Vector2(box_x, box_y),
				Vector2(box_x + box_w, box_y),
				Vector2(box_x + box_w, box_y + box_h),
				Vector2(box_x, box_y + box_h),
			]
		)
		bg.color = Color(0.1, 0.1, 0.1, 0.85)
		_add(bg)

		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var no3: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0

		# N bar (green)
		var n_frac: float = clampf(no3 / 5.0, 0.0, 1.0)
		_add_bar(box_x + 2, box_y + 3, bar_max_w, 5, n_frac, N_COLOR)

		# P bar (purple)
		var p_frac: float = clampf(p_val / 5.0, 0.0, 1.0)
		_add_bar(box_x + 2, box_y + 11, bar_max_w, 5, p_frac, P_COLOR)

		# SOM bar (brown)
		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 1.0)
		_add_bar(box_x + 2, box_y + 19, bar_max_w, 5, som_frac, SOM_COLOR)

		# Labels (tiny, right of bars)
		var lx: float = box_x + bar_max_w + 4
		_add_tiny_label(lx, box_y + 2, "N", N_COLOR)
		_add_tiny_label(lx, box_y + 10, "P", P_COLOR)
		_add_tiny_label(lx, box_y + 18, "S", SOM_COLOR)

		y_off += h


func _add_bar(x: float, y: float, max_w: float, h: float, frac: float, color: Color) -> void:
	# Background track
	var track := Polygon2D.new()
	track.polygon = PackedVector2Array(
		[
			Vector2(x, y),
			Vector2(x + max_w, y),
			Vector2(x + max_w, y + h),
			Vector2(x, y + h),
		]
	)
	track.color = Color(0.25, 0.25, 0.25, 0.5)
	_add(track)
	# Fill bar
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
		_add(fill)


func _add_tiny_label(x: float, y: float, text: String, color: Color) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 7)
	label.add_theme_color_override("font_color", color)
	label.position = Vector2(x, y)
	_add(label)


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
	# Roots drawn along the center seam (x=0) of the cutaway
	var root_start := Vector2(0, HALF_H + 2)
	var root_end := Vector2(0, HALF_H + root_depth)
	var taproot := Line2D.new()
	taproot.points = PackedVector2Array([root_start, root_end])
	taproot.width = clampf(depth_frac * 3.0, 0.5, 2.5)
	taproot.default_color = ROOT_COLOR
	_add(taproot)

	var branch_fracs := [0.1, 0.2, 0.35, 0.5, 0.65]
	for bf: float in branch_fracs:
		if bf > depth_frac:
			break
		var y: float = HALF_H + total_depth * bf
		var density: float = (depth_frac - bf) / depth_frac
		var spread: float = HALF_W * 0.4 * density
		var width: float = 1.5 * density
		if width < 0.3 or spread < 2.0:
			continue
		# Branch into left face
		var left := Line2D.new()
		left.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(-spread * 0.6, y - spread * 0.15),
			]
		)
		left.width = width
		left.default_color = ROOT_COLOR
		_add(left)
		# Branch into right face
		var right := Line2D.new()
		right.points = PackedVector2Array(
			[
				Vector2(0, y),
				Vector2(spread * 0.6, y - spread * 0.15),
			]
		)
		right.width = width
		right.default_color = ROOT_COLOR
		_add(right)
