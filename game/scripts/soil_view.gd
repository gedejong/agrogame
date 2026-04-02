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

## SVG texture paths per soil texture class
const LAYER_TEXTURES := {
	"sand": "res://assets/soil_layers/layer_sandy.svg",
	"sandy_loam": "res://assets/soil_layers/layer_sandy.svg",
	"loam": "res://assets/soil_layers/layer_loam.svg",
	"clay_loam": "res://assets/soil_layers/layer_clay.svg",
	"clay": "res://assets/soil_layers/layer_clay.svg",
	"peat": "res://assets/soil_layers/layer_loam.svg",
}
const LAYER_WET_TEXTURES := {
	"sand": "res://assets/soil_layers/layer_sandy_wet.svg",
	"loam": "res://assets/soil_layers/layer_loam_wet.svg",
	"clay": "res://assets/soil_layers/layer_clay_wet.svg",
}

## Isometric tile half-dimensions (must match TileMapLayer tile size)
const HALF_W := 32.0
const HALF_H := 16.0

## Vertical scale: cm to pixels for layer depth
const DEPTH_SCALE := 0.23

## Overlay colors
const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.5)
const N_COLOR := Color(0.2, 0.75, 0.2, 0.7)
const P_COLOR := Color(0.6, 0.2, 0.75, 0.7)
const SOM_COLOR := Color(0.7, 0.5, 0.2, 0.7)
const ROOT_COLOR := Color(0.55, 0.40, 0.20)

var _active := false
var _cur_parent: Node2D


func show_at(
	tile_pos: Vector2,
	soil_state: Dictionary,
	profile_layers: Array,
	root_depth_cm: float = 0.0,
) -> void:
	show_columns(
		[
			{
				"pos": tile_pos,
				"soil_state": soil_state,
				"profile": profile_layers,
				"root_depth_cm": root_depth_cm,
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
		var rdcm: float = col_data.get("root_depth_cm", 0.0)
		var show_info: bool = col_data.get("show_info", false)
		_build_column(pos, soil_state, profile, rdcm, show_info)
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
	root_depth_cm: float = 0.0,
	show_info: bool = true,
) -> void:
	var container := Node2D.new()
	container.position = pos
	add_child(container)
	_cur_parent = container
	_build_cutaway(soil_state, profile_layers, root_depth_cm, show_info)


func _add(node: Node) -> void:
	_cur_parent.add_child(node)


func _build_cutaway(
	soil_state: Dictionary,
	profile_layers: Array,
	root_depth_cm: float = 0.0,
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
		var depth_darken: float = float(i) * 0.08
		base_color = base_color.darkened(depth_darken)

		# Load soil texture SVG
		var tex_path: String = LAYER_TEXTURES.get(texture, "")
		var soil_tex: Texture2D = load(tex_path) if tex_path else null
		var tex_w := 128.0
		var tex_h := 32.0

		# Left face (shadow side) with texture UV mapping
		var lf := Polygon2D.new()
		lf.polygon = PackedVector2Array(
			[
				Vector2(-HALF_W, y_off),
				Vector2(0, HALF_H + y_off),
				Vector2(0, HALF_H + y_off + h),
				Vector2(-HALF_W, y_off + h),
			]
		)
		if soil_tex:
			lf.texture = soil_tex
			lf.uv = PackedVector2Array(
				[
					Vector2(0, 0),
					Vector2(tex_w, 0),
					Vector2(tex_w, tex_h),
					Vector2(0, tex_h),
				]
			)
			lf.color = Color.WHITE.darkened(0.15 + depth_darken)
		else:
			lf.color = base_color.darkened(0.15)
		_add(lf)

		# Right face (lit side) with texture
		var rf := Polygon2D.new()
		rf.polygon = PackedVector2Array(
			[
				Vector2(0, HALF_H + y_off),
				Vector2(HALF_W, y_off),
				Vector2(HALF_W, y_off + h),
				Vector2(0, HALF_H + y_off + h),
			]
		)
		if soil_tex:
			rf.texture = soil_tex
			rf.uv = PackedVector2Array(
				[
					Vector2(0, 0),
					Vector2(tex_w, 0),
					Vector2(tex_w, tex_h),
					Vector2(0, tex_h),
				]
			)
			rf.color = Color.WHITE.darkened(depth_darken)
		else:
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

	# Single diagonal shadow across the full column height on the right face
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

	# Depth gradient: darkening overlay from top (transparent) to bottom (dark)
	# Covers both faces to simulate decreasing light with depth
	var grad_left := Polygon2D.new()
	grad_left.polygon = PackedVector2Array(
		[
			Vector2(-HALF_W, 0),
			Vector2(0, HALF_H),
			Vector2(0, HALF_H + y_off),
			Vector2(-HALF_W, y_off),
		]
	)
	grad_left.vertex_colors = PackedColorArray(
		[
			Color(0, 0, 0, 0.0),
			Color(0, 0, 0, 0.0),
			Color(0, 0, 0, 0.3),
			Color(0, 0, 0, 0.3),
		]
	)
	_add(grad_left)
	var grad_right := Polygon2D.new()
	grad_right.polygon = PackedVector2Array(
		[
			Vector2(0, HALF_H),
			Vector2(HALF_W, 0),
			Vector2(HALF_W, y_off),
			Vector2(0, HALF_H + y_off),
		]
	)
	grad_right.vertex_colors = PackedColorArray(
		[
			Color(0, 0, 0, 0.0),
			Color(0, 0, 0, 0.0),
			Color(0, 0, 0, 0.3),
			Color(0, 0, 0, 0.3),
		]
	)
	_add(grad_right)

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

	# Root structure using actual simulation depth
	_build_roots(profile_layers, root_depth_cm)


func _build_info_boxes_overlay(
	profile_layers: Array,
	_thetas: Array,
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
	var pad := 3
	var label_w := 12
	var bar_max_w: int = int(box_w - pad * 2 - label_w)
	var y_off := 0.0
	var next_box_y := 0.0
	var marker_positions: Array[Array] = []

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

		# Connector line with outline + endpoint markers
		var p_start := Vector2(HALF_W, layer_mid_y)
		var p_end := Vector2(box_x, box_mid_y)
		var pts := PackedVector2Array([p_start, p_end])
		var line_bg := Line2D.new()
		line_bg.points = pts
		line_bg.width = 3.5
		line_bg.default_color = Color(0, 0, 0, 0.5)
		_add(line_bg)
		var line_fg := Line2D.new()
		line_fg.points = pts
		line_fg.width = 1.5
		line_fg.default_color = Color(0.85, 0.85, 0.85, 0.8)
		_add(line_fg)
		marker_positions.append([p_start, p_end])

		# Box background with border
		var bg := Polygon2D.new()
		var box_pts := PackedVector2Array(
			[
				Vector2(box_x, box_y),
				Vector2(box_x + box_w, box_y),
				Vector2(box_x + box_w, box_y + box_h),
				Vector2(box_x, box_y + box_h),
			]
		)
		bg.polygon = box_pts
		bg.color = Color(0.08, 0.08, 0.08, 0.9)
		_add(bg)
		var border := Line2D.new()
		border.points = box_pts
		border.closed = true
		border.width = 1.0
		border.default_color = Color(0.5, 0.5, 0.5, 0.5)
		_add(border)

		var no3: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0

		var bx: float = box_x + pad
		var n_frac: float = clampf(no3 / 5.0, 0.0, 1.0)
		_add_bar(bx, box_y + 3, bar_max_w, 5, n_frac, N_COLOR)
		var p_frac: float = clampf(p_val / 5.0, 0.0, 1.0)
		_add_bar(bx, box_y + 11, bar_max_w, 5, p_frac, P_COLOR)
		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 1.0)
		_add_bar(bx, box_y + 19, bar_max_w, 5, som_frac, SOM_COLOR)

		var lx: float = box_x + pad + bar_max_w + 2
		_add_tiny_label(lx, box_y + 2, "N", N_COLOR)
		_add_tiny_label(lx, box_y + 10, "P", P_COLOR)
		_add_tiny_label(lx, box_y + 18, "S", SOM_COLOR)

		y_off += h

	# Circle markers drawn last so they render above boxes
	for mp: Array in marker_positions:
		_add_circle_marker(mp[0], 3.0, Color(0.9, 0.9, 0.9, 0.9))
		_add_circle_marker(mp[1], 2.5, Color(0.9, 0.9, 0.9, 0.7))


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


func _add_circle_marker(center: Vector2, radius: float, color: Color) -> void:
	var circle := Polygon2D.new()
	var pts := PackedVector2Array()
	for j in range(10):
		var angle: float = j * TAU / 10.0
		pts.append(center + Vector2(cos(angle), sin(angle)) * radius)
	circle.polygon = pts
	circle.color = color
	_add(circle)
	# Dark outline ring
	var ring := Line2D.new()
	ring.points = pts
	ring.closed = true
	ring.width = 1.0
	ring.default_color = Color(0, 0, 0, 0.5)
	_add(ring)


func _build_roots(profile_layers: Array, root_depth_cm: float = 0.0) -> void:
	## 4 root systems on each face at 1/8, 3/8, 5/8, 7/8 positions,
	## matching the 4x4 plant grid on the tile surface.
	## root_depth_cm comes directly from the simulation.
	if root_depth_cm < 1.0:
		return
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 20.0) * DEPTH_SCALE
	if total_depth <= 0:
		return
	var root_depth: float = root_depth_cm * DEPTH_SCALE * 0.5
	var depth_frac: float = clampf(root_depth / total_depth, 0.0, 1.0)
	var plant_fracs := [0.125, 0.375, 0.625, 0.875]

	# Roots on left face — x positions along the left face width
	for pf: float in plant_fracs:
		var x: float = lerpf(-HALF_W, 0.0, pf)
		var y_base: float = lerpf(0.0, HALF_H, pf)
		_draw_single_root(Vector2(x, y_base), root_depth, depth_frac)

	# Roots on right face — x positions along the right face width
	for pf: float in plant_fracs:
		var x: float = lerpf(0.0, HALF_W, pf)
		var y_base: float = lerpf(HALF_H, 0.0, pf)
		_draw_single_root(Vector2(x, y_base), root_depth, depth_frac)


func _draw_single_root(base: Vector2, root_depth: float, depth_frac: float) -> void:
	var root_end := Vector2(base.x, base.y + root_depth)
	var taproot := Line2D.new()
	taproot.points = PackedVector2Array(
		[
			Vector2(base.x, base.y + 1),
			root_end,
		]
	)
	taproot.width = clampf(depth_frac * 2.0, 0.3, 1.5)
	taproot.default_color = ROOT_COLOR
	_add(taproot)
	# Small lateral branches
	var branch_depths := [0.2, 0.5]
	for bd: float in branch_depths:
		if bd > depth_frac:
			break
		var y: float = base.y + root_depth * bd
		var spread: float = 4.0 * (1.0 - bd)
		if spread < 1.0:
			continue
		var br := Line2D.new()
		br.points = PackedVector2Array(
			[
				Vector2(base.x, y),
				Vector2(base.x + spread, y + 2),
			]
		)
		br.width = 0.7
		br.default_color = ROOT_COLOR
		_add(br)
