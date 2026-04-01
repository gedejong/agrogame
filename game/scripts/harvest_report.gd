extends Control
## End-of-season harvest report screen (#116).
## Shows yield/GYGA grade, P&L, soil health, and Next Season button.

const GRADE_COLORS := {
	"A": Color(0.2, 0.8, 0.2),
	"B": Color(0.5, 0.8, 0.2),
	"C": Color(0.9, 0.8, 0.1),
	"D": Color(0.9, 0.5, 0.1),
	"F": Color(0.9, 0.2, 0.2),
}

var _game_id: String = ""
var _api_client: Node

@onready var title_label: Label = $VBox/TitleLabel
@onready var yield_container: VBoxContainer = $VBox/YieldSection
@onready var pnl_container: VBoxContainer = $VBox/PnLSection
@onready var soil_container: VBoxContainer = $VBox/SoilHealthSection
@onready var credits_label: Label = $VBox/CreditsLabel
@onready var next_season_btn: Button = $VBox/NextSeasonButton


func _ready() -> void:
	_api_client = preload("res://scripts/api_client.gd").new()
	add_child(_api_client)
	next_season_btn.pressed.connect(_on_next_season)
	next_season_btn.disabled = true


func load_report(game_id: String) -> void:
	_game_id = game_id
	title_label.text = "Loading report..."
	_api_client.get_report(game_id, _on_report_received)


func _on_report_received(success: bool, data: Dictionary) -> void:
	if not success:
		title_label.text = "Failed to load report"
		return
	_display_report(data)
	next_season_btn.disabled = false


func _display_report(data: Dictionary) -> void:
	var season: int = data.get("season_number", 0)
	var start: String = data.get("start_date", "")
	var end_d: String = data.get("end_date", "")
	title_label.text = "Harvest Report — Season %d (%s → %s)" % [season, start, end_d]

	# Yield section
	_clear_children(yield_container)
	var header := Label.new()
	header.text = "Yield per Patch"
	header.add_theme_font_size_override("font_size", 16)
	yield_container.add_child(header)

	var patches: Dictionary = data.get("patches", {})
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		for patch: Dictionary in patch_list:
			var grain: float = patch.get("grain_t_ha", 0.0)
			var gyga: float = patch.get("gyga_potential_t_ha", 0.0)
			var grade: String = patch.get("grade", "?")
			var soil: String = patch.get("soil_profile", "")
			var ratio: float = patch.get("yield_ratio", 0.0)
			var line := Label.new()
			line.text = (
				"  %s: %.1f t/ha (%.0f%% of %.1f potential) — %s"
				% [soil, grain, ratio * 100, gyga, grade]
			)
			var grade_color: Color = GRADE_COLORS.get(grade, Color.WHITE)
			line.add_theme_color_override("font_color", grade_color)
			line.add_theme_font_size_override("font_size", 14)
			yield_container.add_child(line)

	# P&L section
	_clear_children(pnl_container)
	var pnl_header := Label.new()
	pnl_header.text = "Profit & Loss"
	pnl_header.add_theme_font_size_override("font_size", 16)
	pnl_container.add_child(pnl_header)

	var revenue: int = data.get("revenue_credits", 0)
	var total_cost: int = data.get("total_cost_credits", 0)
	var profit: int = data.get("profit_credits", 0)

	_add_pnl_line("  Revenue: %d credits" % revenue, Color(0.3, 0.8, 0.3))
	_add_pnl_line("  Costs: -%d credits" % total_cost, Color(0.8, 0.3, 0.3))

	var costs: Array = data.get("costs", [])
	for cost: Dictionary in costs:
		var cat: String = cost.get("category", "")
		var amt: int = cost.get("amount_credits", 0)
		_add_pnl_line("    %s: -%d" % [cat, amt], Color(0.7, 0.5, 0.5))

	var profit_color := Color(0.3, 0.9, 0.3) if profit >= 0 else Color(0.9, 0.3, 0.3)
	_add_pnl_line("  Net: %d credits" % profit, profit_color)

	# Soil health
	_clear_children(soil_container)
	var soil_header := Label.new()
	soil_header.text = "Soil Health"
	soil_header.add_theme_font_size_override("font_size", 16)
	soil_container.add_child(soil_header)

	for field_key2: String in patches:
		var patch_list2: Array = patches[field_key2]
		for patch2: Dictionary in patch_list2:
			var soil2: String = patch2.get("soil_profile", "")
			var som2: float = patch2.get("som_total_c_g_m2", 0.0)
			var theta2: float = patch2.get("theta_surface", 0.0)
			var som_label := Label.new()
			som_label.text = "  %s: SOM %.0f gC/m² | θ %.3f" % [soil2, som2, theta2]
			som_label.add_theme_font_size_override("font_size", 13)
			soil_container.add_child(som_label)

	# Credits
	var balance_before: int = data.get("balance_before", 0)
	var balance_after: int = data.get("balance_after", 0)
	var delta: int = data.get("balance_delta", 0)
	var delta_str := "+%d" % delta if delta >= 0 else "%d" % delta
	var delta_color := Color(0.3, 0.9, 0.3) if delta >= 0 else Color(0.9, 0.3, 0.3)
	credits_label.text = "Credits: %d → %d (%s)" % [balance_before, balance_after, delta_str]
	credits_label.add_theme_color_override("font_color", delta_color)


func _add_pnl_line(text: String, color: Color) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 13)
	label.add_theme_color_override("font_color", color)
	pnl_container.add_child(label)


func _clear_children(container: Control) -> void:
	for child in container.get_children():
		child.queue_free()


func _on_next_season() -> void:
	get_tree().change_scene_to_file("res://scenes/farm_view.tscn")
