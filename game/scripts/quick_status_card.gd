class_name QuickStatusCard
extends PanelContainer
## Compact tile status card with 4 health gauges + recommendation.
## Shown on tile click. Progressive disclosure: click gauge → details.
## Ref: Shneiderman 1996 — Overview first, details on demand.

signal history_requested
signal soil_view_requested

const GAUGE_DEFS: Array[Dictionary] = [
	{"key": "water", "icon": "💧", "label": "Water"},
	{"key": "nutrient", "icon": "🌿", "label": "Nutrients"},
	{"key": "growth", "icon": "📈", "label": "Growth"},
	{"key": "soil", "icon": "🏗", "label": "Soil"},
]

## Traffic light thresholds.
const GOOD_THRESHOLD := 70.0
const WARN_THRESHOLD := 40.0

## Soil health reference values.
## SOM: 2000 gC/m² is a well-managed agricultural soil (Ref: Brady & Weil 2017).
const SOM_REFERENCE_C_G_M2 := 2000.0
## Theta: 0.25 m³/m³ is near field capacity for loam (Ref: FAO-56, Table 3).
const THETA_OPTIMAL := 0.25
const THETA_RANGE := 0.25

## Expected peak LAI by crop key (Ref: WOFOST crop parameters).
const CROP_MAX_LAI := {
	"maize": 6.0,
	"spring_wheat": 4.0,
	"winter_wheat": 4.5,
	"sorghum": 5.0,
	"rice": 5.0,
	"grape": 3.0,
}

var _gauge_labels: Dictionary = {}
var _recommendation_label: Label = null
var _tile_label: Label = null


func show_status(tile_data: Dictionary, soil_type: String) -> void:
	_clear()
	var style := UiTheme.create_panel_style()
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	add_theme_stylebox_override("panel", style)
	UiTheme.add_blur_bg(self)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)
	add_child(vbox)

	# Tile header
	_tile_label = Label.new()
	var crop_key: String = tile_data.get("crop_key", "")
	var crop_text: String = crop_key.capitalize() if not crop_key.is_empty() else "Empty"
	_tile_label.text = "%s — %s" % [crop_text, soil_type]
	_tile_label.add_theme_font_size_override("font_size", 12)
	_tile_label.add_theme_color_override("font_color", UiTheme.TEXT_PRIMARY)
	_tile_label.uppercase = true
	_tile_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(_tile_label)

	_add_separator(vbox)

	# 4 gauges
	var scores: Dictionary = compute_scores(tile_data)
	for def: Dictionary in GAUGE_DEFS:
		var score: float = scores.get(def["key"], 0.0)
		_add_gauge_row(vbox, def, score)

	_add_separator(vbox)

	# Recommendation
	_recommendation_label = Label.new()
	_recommendation_label.text = compute_recommendation(tile_data, scores)
	_recommendation_label.add_theme_font_size_override("font_size", 10)
	_recommendation_label.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	_recommendation_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	vbox.add_child(_recommendation_label)

	# Action buttons
	var btn_row := HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 8)
	btn_row.alignment = BoxContainer.ALIGNMENT_CENTER
	var history_btn := Button.new()
	history_btn.text = "History"
	history_btn.add_theme_font_size_override("font_size", 10)
	UiTheme.style_button(history_btn)
	history_btn.pressed.connect(func() -> void: history_requested.emit())
	btn_row.add_child(history_btn)
	var soil_btn := Button.new()
	soil_btn.text = "View Soil"
	soil_btn.add_theme_font_size_override("font_size", 10)
	UiTheme.style_button(soil_btn)
	soil_btn.pressed.connect(func() -> void: soil_view_requested.emit())
	btn_row.add_child(soil_btn)
	vbox.add_child(btn_row)


func _add_gauge_row(parent: VBoxContainer, def: Dictionary, score: float) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	# Icon
	var icon := Label.new()
	icon.text = def["icon"]
	icon.add_theme_font_size_override("font_size", 16)
	icon.custom_minimum_size.x = 24
	row.add_child(icon)
	# Label
	var lbl := Label.new()
	lbl.text = def["label"]
	lbl.add_theme_font_size_override("font_size", 11)
	lbl.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	lbl.custom_minimum_size.x = 64
	row.add_child(lbl)
	# Score value (large colored number)
	var val := Label.new()
	val.text = "%d" % int(score)
	val.add_theme_font_size_override("font_size", 20)
	val.add_theme_color_override("font_color", _score_color(score))
	val.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	val.custom_minimum_size.x = 40
	row.add_child(val)
	# Warning indicator
	if score < WARN_THRESHOLD:
		var warn := Label.new()
		warn.text = " ⚠"
		warn.add_theme_font_size_override("font_size", 14)
		warn.add_theme_color_override("font_color", UiTheme.ACCENT_RED)
		row.add_child(warn)
	elif score < GOOD_THRESHOLD:
		var warn := Label.new()
		warn.text = " !"
		warn.add_theme_font_size_override("font_size", 14)
		warn.add_theme_color_override("font_color", UiTheme.ACCENT_GOLD)
		row.add_child(warn)
	_gauge_labels[def["key"]] = val
	parent.add_child(row)


static func compute_scores(tile_data: Dictionary) -> Dictionary:
	"""Compute 4 health scores (0-100) from raw tile data."""
	# Water: water_stress is 1.0=healthy, 0.0=severe
	var water_s: float = tile_data.get("water_stress", 1.0)
	var water: float = clampf(water_s * 100.0, 0.0, 100.0)
	# Nutrients: Liebig minimum of all nutrient stresses.
	# Stress values are 0=healthy, 1=severe (inverted from API).
	# Convert: score = (1 - max_stress) * 100
	var n_s: float = tile_data.get("n_stress", 0.0)
	var p_s: float = tile_data.get("p_stress", 0.0)
	var fe_s: float = tile_data.get("fe_stress", 0.0)
	var zn_s: float = tile_data.get("zn_stress", 0.0)
	var worst_nutrient: float = maxf(maxf(n_s, p_s), maxf(fe_s, zn_s))
	var nutrient: float = clampf((1.0 - worst_nutrient) * 100.0, 0.0, 100.0)
	# Growth: LAI relative to crop-specific expected LAI for this stage
	var lai: float = tile_data.get("lai", 0.0)
	var stage: int = tile_data.get("crop_stage", 0)
	var crop_key: String = tile_data.get("crop_key", "")
	var expected_lai: float = _expected_lai_for_stage(stage, crop_key)
	var growth: float = (
		100.0 if stage == 0 else clampf(lai / maxf(expected_lai, 0.1) * 100.0, 0.0, 100.0)
	)
	# Soil: composite of SOM, theta relative to optimal
	var som: float = tile_data.get("som_total_c_g_m2", 0.0)
	var theta: float = tile_data.get("theta_surface", 0.0)
	var som_score: float = clampf(som / SOM_REFERENCE_C_G_M2 * 100.0, 0.0, 100.0)
	var theta_score: float = clampf(
		(1.0 - absf(theta - THETA_OPTIMAL) / THETA_RANGE) * 100.0, 0.0, 100.0
	)
	var soil: float = (som_score + theta_score) * 0.5
	return {"water": water, "nutrient": nutrient, "growth": growth, "soil": soil}


static func _expected_lai_for_stage(stage: int, crop_key: String = "") -> float:
	var max_lai: float = CROP_MAX_LAI.get(crop_key, 5.0)
	match stage:
		1:
			return max_lai * 0.15
		2:
			return max_lai * 0.7
		3:
			return max_lai * 0.95
		4:
			return max_lai * 0.7
	return 1.0


static func compute_recommendation(tile_data: Dictionary, scores: Dictionary) -> String:
	"""Simple rule-based action recommendation."""
	var crop: String = tile_data.get("crop_key", "")
	if crop.is_empty():
		return "No crop planted. Consider planting."
	# Find worst score
	var worst_key: String = "water"
	var worst_val: float = 100.0
	for key: String in scores:
		if scores[key] < worst_val:
			worst_val = scores[key]
			worst_key = key
	if worst_val >= GOOD_THRESHOLD:
		return "All systems healthy."
	match worst_key:
		"water":
			return "Soil drying out. Consider irrigating."
		"nutrient":
			if tile_data.get("n_stress", 0.0) > 0.3:
				return "Nitrogen low. Consider fertilizing."
			if tile_data.get("p_stress", 0.0) > 0.3:
				return "Phosphorus low. Apply TSP fertilizer."
			return "Micronutrient deficiency detected."
		"growth":
			return "Growth below expected. Check water and nutrients."
		"soil":
			return "Soil health declining. Reduce tillage or add organic matter."
	return ""


static func _score_color(score: float) -> Color:
	if score >= GOOD_THRESHOLD:
		return UiTheme.ACCENT_GREEN
	if score >= WARN_THRESHOLD:
		return UiTheme.ACCENT_GOLD
	return UiTheme.ACCENT_RED


func _add_separator(parent: VBoxContainer) -> void:
	var sep := HSeparator.new()
	var s := StyleBoxFlat.new()
	s.bg_color = UiTheme.SEPARATOR_COLOR
	s.content_margin_top = 3
	s.content_margin_bottom = 3
	sep.add_theme_stylebox_override("separator", s)
	parent.add_child(sep)


func _clear() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_gauge_labels.clear()
