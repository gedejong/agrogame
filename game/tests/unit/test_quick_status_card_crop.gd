extends GutTest
## QuickStatusCard's crop-status block and fixed width (#630).

const QSC = preload("res://scripts/quick_status_card.gd")


func _show(tile: Dictionary, warned: bool = false) -> PanelContainer:
	tile.merge({"water_stress": 0.0 if warned else 1.0, "n_stress": 1.0 if warned else 0.0})
	if warned:
		tile.merge({"lai": 0.0, "crop_stage": 2, "theta_surface": 0.0})
	var card: PanelContainer = QSC.new()
	add_child_autofree(card)
	card.show_status(tile, "Sand - Temperate")
	return card


func _texts(node: Node) -> Array:
	var out: Array = []
	for child in node.get_children():
		if child is Label:
			out.append(child.text)
		out.append_array(_texts(child))
	return out


func test_card_shows_stage_roots_and_damage_rows() -> void:
	var tile := {
		"crop_key": "maize",
		"crop_stage_name": "vegetative",
		"dev_stage": 0.141,
		"root_depth_cm": 12.7,
		"heat_days": 24,
		"heat_threshold": 35.0,
		"frost_days": 2,
		"frost_lai": 0.4,
		"frost_threshold": 0.0,
	}
	var texts := _texts(_show(tile))
	assert_has(texts, "Vegetative · DVS 0.14")
	assert_has(texts, "Roots 13 cm")
	assert_has(texts, "Heat: 24 days above 35 °C during flowering or grain fill")
	assert_has(texts, "Frost: 2 days below 0 °C, LAI −0.40")


func test_card_for_a_bare_tile_reads_dashes_and_no_damage_row() -> void:
	var texts := _texts(_show({"crop_key": ""}))
	assert_has(texts, "—")
	assert_has(texts, "Roots —")
	assert_eq(texts.filter(func(t: String) -> bool: return t.begins_with("Heat")), [])


func test_stage_row_carries_the_bbch_tooltip() -> void:
	var card := _show({"crop_key": "maize", "crop_stage_name": "grain_fill", "dev_stage": 1.2})
	var tips: Array = []
	for lbl: Label in card.find_children("*", "Label", true, false):
		if lbl.tooltip_text != "":
			tips.append(lbl.tooltip_text)
	assert_eq(tips.size(), 1)
	assert_string_contains(tips[0], "BBCH 71–85")


func test_damage_rows_are_tinted_like_their_icons() -> void:
	var card := _show(
		{"crop_key": "maize", "heat_days": 1, "heat_threshold": 35.0, "frost_days": 1}
	)
	var colors: Dictionary = {}
	for lbl: Label in card.find_children("*", "Label", true, false):
		colors[lbl.text.get_slice(":", 0)] = lbl.get_theme_color("font_color")
	assert_eq(colors["Heat"], UiTheme.SUBSTANCE_HEAT)
	assert_eq(colors["Frost"], UiTheme.SUBSTANCE_FROST)


func test_card_width_is_fixed_narrow_or_wide() -> void:
	var narrow := _show({"crop_key": ""})
	var wide := _show(
		{
			"crop_key": "grape",
			"crop_stage_name": "maturity",
			"root_depth_cm": 100.0,
			"heat_days": 24,
			"heat_threshold": 38.0,
			"frost_days": 11,
			"frost_lai": 2.03,
		},
		true
	)
	await wait_process_frames(2)
	assert_eq(narrow.size.x, QSC.WIDTH, "narrowest state")
	assert_eq(wide.size.x, QSC.WIDTH, "widest state: a long line wraps")


func test_a_long_soil_name_wraps_instead_of_widening_the_card() -> void:
	var card: PanelContainer = QSC.new()
	add_child_autofree(card)
	card.show_status({"crop_key": "maize"}, "Sandy - Sub-Saharan Variant")
	await wait_process_frames(2)
	assert_eq(card.size.x, QSC.WIDTH)


func test_history_panel_opens_beside_the_card_not_on_it() -> void:
	var pos: Vector2 = QSC.history_position()
	assert_eq(pos, Vector2(QSC.ORIGIN.x + QSC.WIDTH + QSC.HISTORY_GAP, QSC.ORIGIN.y))
	var card := _show({"crop_key": ""}, true)
	card.position = QSC.ORIGIN
	await wait_process_frames(2)
	var panel := Rect2(pos, Vector2(240, 300))
	assert_false(card.get_rect().intersects(panel), "no overlap")
