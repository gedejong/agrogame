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
const SOM_COLOR := Color(0.2, 0.15, 0.05, 0.5)
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


func _build_cutaway(soil_state: Dictionary, profile_layers: Array, crop_stage: String = "") -> void:
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

	var y_off := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var h: float = depth_cm * DEPTH_SCALE
		var texture: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.45)
		var base_color: Color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)

		# Left face: left vertex (-HW, 0) to bottom vertex (0, HH), dropped by y_off
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
		add_child(lf)

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
		add_child(rf)

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
			add_child(wl)
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
			add_child(wr)

		# SOM band on left face (dark strip at top of layer)
		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0
		var som_frac: float = clampf((lab + stab) / 50000.0, 0.0, 0.8)
		if som_frac > 0.02:
			var sh: float = maxf(h * 0.25, 2.0)
			var som := Polygon2D.new()
			som.polygon = PackedVector2Array(
				[
					Vector2(-HALF_W, y_off),
					Vector2(-HALF_W + HALF_W * som_frac, y_off),
					Vector2(-HALF_W + HALF_W * som_frac, y_off + sh),
					Vector2(-HALF_W, y_off + sh),
				]
			)
			som.color = SOM_COLOR
			add_child(som)

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
		add_child(edge)

		y_off += h

	# Outline edges for visual separation from surroundings
	_build_outline(y_off)

	# Summary label below cutaway
	_build_label(y_off, thetas, no3_arr, p_arr, profile_layers)

	# Root structure (depth tied to crop stage)
	_build_roots(profile_layers, crop_stage)


func _build_outline(total_y: float) -> void:
	## Draw dark outline around the cutaway for visual separation.
	var outline := Line2D.new()
	outline.points = PackedVector2Array(
		[
			Vector2(-HALF_W, 0),
			Vector2(-HALF_W, total_y),
			Vector2(0, HALF_H + total_y),
			Vector2(HALF_W, total_y),
			Vector2(HALF_W, 0),
		]
	)
	outline.width = 1.5
	outline.default_color = Color(0, 0, 0, 0.6)
	add_child(outline)


func _build_label(
	total_y: float,
	thetas: Array,
	no3_arr: Array,
	p_arr: Array,
	profile_layers: Array,
) -> void:
	## Compact text summary below the cutaway.
	var theta_top: float = thetas[0] if thetas.size() > 0 else 0.0
	var no3_top: float = no3_arr[0] if no3_arr.size() > 0 else 0.0
	var p_top: float = p_arr[0] if p_arr.size() > 0 else 0.0
	var tex: String = profile_layers[0].get("texture", "?") if profile_layers.size() > 0 else "?"

	var label := Label.new()
	label.text = "%s | θ%.2f | N%.1f | P%.1f" % [tex, theta_top, no3_top, p_top]
	label.add_theme_font_size_override("font_size", 9)
	label.add_theme_color_override("font_color", Color(0.9, 0.9, 0.9))
	label.position = Vector2(-HALF_W, HALF_H + total_y + 4)
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
	# Roots drawn along the center seam (x=0) of the cutaway
	var root_start := Vector2(0, HALF_H + 2)
	var root_end := Vector2(0, HALF_H + root_depth)
	var taproot := Line2D.new()
	taproot.points = PackedVector2Array([root_start, root_end])
	taproot.width = clampf(depth_frac * 3.0, 0.5, 2.5)
	taproot.default_color = ROOT_COLOR
	add_child(taproot)

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
		add_child(left)
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
		add_child(right)
