class_name QuickStatusCard
extends PanelContainer
## Compact tile status card with 4 health gauges + recommendation.
## Shown on tile click. Progressive disclosure: click gauge → details.
## Ref: Shneiderman 1996 — Overview first, details on demand.

signal history_requested
signal soil_view_requested

## Fixed card width (px), at least its widest content (four gauges each with a
## warning mark is about 194), so the History panel can sit beside it and never
## on it (#630).
const WIDTH := 200.0
## Where the card sits, and the gap the History panel keeps from it.
const ORIGIN := Vector2(16, 40)
const HISTORY_GAP := 8.0

## The four gauges and their tooltips (#660). Each reads an engine quantity:
## Water today's Ks (Ta/Tp), Nutrients the Liebig minimum the canopy applies,
## Growth actual over potential-production biomass (van Ittersum & Rabbinge
## 1997), Root-zone water available over total available water (FAO-56 Eq. 82).
const GAUGE_DEFS: Array[Dictionary] = [
	{
		"key": "water",
		"icon": "💧",
		"label": "Water",
		"tip":
		(
			"Water supply today: actual over potential transpiration (Ks)."
			+ " The drought alert fires below 40."
		),
	},
	{
		"key": "nutrient",
		"icon": "🌿",
		"label": "Nutrients",
		"tip": "Scarcest nutrient today (N, P, S, Fe, Zn, Mn), the one limiting growth.",
	},
	{
		"key": "growth",
		"icon": "📈",
		"label": "Growth",
		"tip":
		(
			"Biomass so far as a share of what this crop would have grown"
			+ " without water or nutrient shortage."
		),
	},
	{
		"key": "root_zone",
		"icon": "🏗",
		"label": "Root zone",
		"tip":
		(
			"Plant-available water left in the root zone. '!' once the crop's"
			+ " readily available water (FAO-56) is used up."
		),
	},
]

## Marks: ⚠ below 40, ADR-017's drought alert threshold (Ks 0.40); ! below 70,
## the card's amber band.
const GOOD_THRESHOLD := 70.0
const WARN_THRESHOLD := 40.0
## ADR-017 n_stress_threshold: the N alert's condition, so card and alert agree.
const N_ALERT_THRESHOLD := 0.90
## A gauge that does not apply shows "—".
const NOT_SHOWN := -1.0
const STANDING_STAGES: Array[String] = ["emerged", "vegetative", "flowering", "grain_fill"]
## Stages in which the ADR-017 N alert fires and N fertilizer still pays.
const N_ALERT_STAGES: Array[String] = ["emerged", "vegetative", "flowering"]
## Tile stress key prefix to nutrient name, in the Liebig order N, P, S, Fe, Zn, Mn.
const NUTRIENT_NAMES := {
	"n": "nitrogen", "p": "phosphorus", "s": "sulfur", "fe": "iron", "zn": "zinc", "mn": "manganese"
}

var _gauge_labels: Dictionary = {}
var _recommendation_label: Label = null
var _tile_label: Label = null


## Where the History panel opens: right of the card, never over it.
static func history_position() -> Vector2:
	return ORIGIN + Vector2(WIDTH + HISTORY_GAP, 0.0)


func show_status(tile_data: Dictionary, soil_type: String) -> void:
	_clear()
	custom_minimum_size.x = WIDTH
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
	_tile_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART  # a long soil name wraps (#630)
	vbox.add_child(_tile_label)

	_add_separator(vbox)

	# 4 gauges
	var scores: Dictionary = compute_scores(tile_data)
	var live: bool = String(tile_data.get("crop_stage_name", "")) in STANDING_STAGES
	for def: Dictionary in GAUGE_DEFS:
		var key: String = def["key"]
		var mark := gauge_mark(key, tile_data, scores)
		var tip: String = def["tip"]
		if key == "nutrient" and live:
			tip += " " + limiting_text(tile_data)
		_add_gauge_row(vbox, def, scores[key], mark, _value_color(mark, live), tip)

	_add_separator(vbox)

	_add_crop_status(vbox, tile_data)
	_add_separator(vbox)

	# Recommendation
	_recommendation_label = Label.new()
	_recommendation_label.text = compute_recommendation(tile_data)
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


## Stage, roots and damage rows (#630). Labels wrap, so a long line never widens
## the card.
func _add_crop_status(parent: VBoxContainer, tile_data: Dictionary) -> void:
	var crop_key: String = tile_data.get("crop_key", "")
	var stage_name: String = tile_data.get("crop_stage_name", "")
	var stage := _add_status_label(
		parent, CropStatus.stage_text(stage_name, tile_data.get("dev_stage", -1.0), crop_key)
	)
	stage.tooltip_text = CropStatus.stage_tooltip(stage_name, crop_key)
	stage.mouse_filter = Control.MOUSE_FILTER_STOP
	_add_status_label(parent, CropStatus.root_text(tile_data.get("root_depth_cm", 0.0), crop_key))
	for line: Dictionary in CropStatus.damage_lines(tile_data):
		var tint: Color = (
			UiTheme.SUBSTANCE_HEAT if line["kind"] == "heat" else UiTheme.SUBSTANCE_FROST
		)
		_add_status_label(parent, line["text"]).add_theme_color_override("font_color", tint)


func _add_status_label(parent: VBoxContainer, text: String) -> Label:
	var lbl := Label.new()
	lbl.text = text
	lbl.add_theme_font_size_override("font_size", 11)
	lbl.add_theme_color_override("font_color", UiTheme.TEXT_PRIMARY)
	lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(lbl)
	return lbl


func _add_gauge_row(
	parent: VBoxContainer, def: Dictionary, score: float, mark: String, color: Color, tip: String
) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	row.tooltip_text = tip
	row.mouse_filter = Control.MOUSE_FILTER_PASS
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
	# Score value (large colored number), "—" when the gauge does not apply
	var val := Label.new()
	val.text = "—" if score < 0.0 else "%d" % floori(score + 1e-6)
	val.add_theme_font_size_override("font_size", 20)
	val.add_theme_color_override("font_color", color)
	val.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	val.custom_minimum_size.x = 40
	row.add_child(val)
	if not mark.is_empty():
		var warn := Label.new()
		warn.text = " " + mark
		warn.add_theme_font_size_override("font_size", 14)
		warn.add_theme_color_override("font_color", color)
		row.add_child(warn)
	_gauge_labels[def["key"]] = val
	parent.add_child(row)


## Gauge values 0-100 from one tile, NOT_SHOWN where a gauge does not apply
## (#660): Water and Nutrients while the crop stands (emerged to grain fill),
## Growth then and at maturity, Root-zone water whenever the reply carried it.
static func compute_scores(tile_data: Dictionary) -> Dictionary:
	var stage: String = tile_data.get("crop_stage_name", "")
	var standing: bool = stage in STANDING_STAGES
	var growth: float = tile_data.get("growth_vs_potential", NOT_SHOWN)
	var rzf: float = tile_data.get("root_zone_water_fraction", NOT_SHOWN)
	var water: float = tile_data.get("water_ks", 1.0)
	var nutrient: float = limiting_nutrient(tile_data)["value"]
	var growth_shown: bool = (standing or stage == "maturity") and growth >= 0.0
	return {
		"water": _pct(water) if standing else NOT_SHOWN,
		"nutrient": _pct(nutrient) if standing else NOT_SHOWN,
		"growth": _pct(growth) if growth_shown else NOT_SHOWN,
		"root_zone": _pct(minf(rzf, 1.0)) if rzf >= 0.0 else NOT_SHOWN,
	}


static func _pct(fraction: float) -> float:
	return clampf(fraction * 100.0, 0.0, 100.0)


## The scarcest nutrient: {"name", "value"}, value 1.0 = unlimited. Tiles hold
## stress as 1 - value, 0 = none.
static func limiting_nutrient(tile_data: Dictionary) -> Dictionary:
	var name := ""
	var worst := 0.0
	for key: String in NUTRIENT_NAMES:
		var stress: float = tile_data.get(key + "_stress", 0.0)
		if stress > worst:
			worst = stress
			name = NUTRIENT_NAMES[key]
	return {"name": name, "value": 1.0 - worst}


## "Limiting: zinc 0.89.", or "Limiting: none." on an unlimited crop.
static func limiting_text(tile_data: Dictionary) -> String:
	var lim := limiting_nutrient(tile_data)
	if String(lim["name"]).is_empty():
		return "Limiting: none."
	return "Limiting: %s %.2f." % [lim["name"], lim["value"]]


## N as the ADR-017 alert reads it, when the alert's stage gate is open.
static func _n_alert(tile_data: Dictionary) -> bool:
	var n: float = 1.0 - float(tile_data.get("n_stress", 0.0))
	return tile_data.get("crop_stage_name", "") in N_ALERT_STAGES and n < N_ALERT_THRESHOLD


## Root-zone water below the crop's readily available water: fraction < 1 - p.
static func _root_zone_dry(tile_data: Dictionary) -> bool:
	var p: float = tile_data.get("depletion_fraction_p", NOT_SHOWN)
	var rzf: float = tile_data.get("root_zone_water_fraction", NOT_SHOWN)
	return p > 0.0 and rzf >= 0.0 and rzf < 1.0 - p


## The gauge's mark, "", "!" or "⚠", only while the crop stands (#660).
## Root-zone water gets a gold "!" below 1 - p and never ⚠.
static func gauge_mark(key: String, tile_data: Dictionary, scores: Dictionary) -> String:
	var score: float = scores[key]
	if score < 0.0 or not String(tile_data.get("crop_stage_name", "")) in STANDING_STAGES:
		return ""
	if key == "root_zone":
		return "!" if _root_zone_dry(tile_data) else ""
	if score < WARN_THRESHOLD:
		return "⚠"
	if score < GOOD_THRESHOLD or (key == "nutrient" and _n_alert(tile_data)):
		return "!"
	return ""


## The gauge the advice acts on: "water", "nutrient", "root_zone", or "" when
## the advice asks for no action (#660 §6; the field strip's attention, #602).
## First match wins: no gauge on a crop that does not stand (bare, sown, mature),
## then the lower of Ks < 0.70 and the nutrient limit (a tie goes to water),
## then a drying root zone. Growth behind potential is never one: it is the
## outcome of earlier limits, and its advice asks for no action.
static func advised_gauge(tile_data: Dictionary) -> String:
	if String(tile_data.get("crop_key", "")).is_empty():
		return ""
	if not String(tile_data.get("crop_stage_name", "")) in STANDING_STAGES:
		return ""
	var ks: float = tile_data.get("water_ks", 1.0)
	var nut := _nutrient_candidate(tile_data)
	if ks < GOOD_THRESHOLD / 100.0 and (nut.is_empty() or ks <= nut["value"]):
		return "water"
	if not nut.is_empty():
		return "nutrient"
	return "root_zone" if _root_zone_dry(tile_data) else ""


## Advice naming the true limit (#660 §6). First match wins: no crop, not
## emerged, mature, then the advised gauge, then growth behind potential.
static func compute_recommendation(tile_data: Dictionary) -> String:
	if String(tile_data.get("crop_key", "")).is_empty():
		return "No crop planted. Consider planting."
	var stage: String = tile_data.get("crop_stage_name", "")
	if stage == "maturity":
		return "Mature: ready to harvest."
	if not stage in STANDING_STAGES:
		return "Sown, not yet emerged."
	match advised_gauge(tile_data):
		"water":
			if float(tile_data.get("water_ks", 1.0)) < WARN_THRESHOLD / 100.0:
				return "Crop is short of water. Irrigate now."
			return "Crop is starting to run short of water. Consider irrigating."
		"nutrient":
			return _nutrient_advice(_nutrient_candidate(tile_data)["name"], stage)
		"root_zone":
			return "Root zone is drying. Irrigate before the crop shows stress."
	var growth: float = tile_data.get("growth_vs_potential", NOT_SHOWN)
	if growth >= 0.0 and growth < GOOD_THRESHOLD / 100.0:
		return "Growth is behind its potential after earlier stress or damage."
	return "No action needed."


## The nutrient advice candidate: the scarcest nutrient below 0.70, else N below
## the ADR-017 alert threshold while the alert's stages are open; {} if none.
static func _nutrient_candidate(tile_data: Dictionary) -> Dictionary:
	var lim := limiting_nutrient(tile_data)
	if lim["value"] < GOOD_THRESHOLD / 100.0:
		return lim
	if _n_alert(tile_data):
		return {"name": "nitrogen", "value": 1.0 - float(tile_data.get("n_stress", 0.0))}
	return {}


static func _nutrient_advice(name: String, stage: String) -> String:
	match name:
		"nitrogen":
			if stage in N_ALERT_STAGES:
				return "Nitrogen is limiting growth. Apply urea or ammonium nitrate."
			# ADR-017: the #470 playtest found no grain response from about 15
			# days into grain fill.
			return "Nitrogen is limiting growth, but fertilizer this late adds little yield."
		"phosphorus":
			return "Phosphorus is limiting growth. Apply TSP."
	# No S product is priced until #509.
	return "%s is limiting growth." % name.capitalize()


## Value colour follows the mark; an unmarked live gauge is green and a gauge
## off season (Growth at maturity, Root-zone water on a bare tile) is neutral.
static func _value_color(mark: String, live: bool) -> Color:
	if mark == "⚠":
		return UiTheme.ACCENT_RED
	if mark == "!":
		return UiTheme.ACCENT_GOLD
	return UiTheme.ACCENT_GREEN if live else UiTheme.TEXT_SECONDARY


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
