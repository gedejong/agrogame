extends GutTest
## Per-layer pH readout in the nutrient panel (#465). Split from
## test_nutrient_panel.gd to stay within gdlint max-public-methods.

const NutrientPanel = preload("res://scripts/nutrient_panel.gd")


func test_format_ph_one_decimal() -> void:
	# AC #10: one value per layer, one decimal.
	assert_eq(NutrientPanel.format_ph(5.0), "5.0", "acid value")
	assert_eq(NutrientPanel.format_ph(6.84), "6.8", "neutral value")
	assert_eq(NutrientPanel.format_ph(8.0), "8.0", "alkaline value")


func test_ph_band_names_acid_optimal_alkaline() -> void:
	assert_eq(NutrientPanel.ph_band(5.0), "acid")
	assert_eq(NutrientPanel.ph_band(6.8), "optimal")
	assert_eq(NutrientPanel.ph_band(8.0), "alkaline")
	# Band edges are inclusive of the optimal range.
	assert_eq(NutrientPanel.ph_band(NutrientPanel.PH_OPT_MIN), "optimal")
	assert_eq(NutrientPanel.ph_band(NutrientPanel.PH_OPT_MAX), "optimal")


func test_ph_band_color_distinguishes_acid_from_alkaline() -> void:
	var acid: Color = NutrientPanel.ph_band_color(5.0)
	var optimal: Color = NutrientPanel.ph_band_color(6.8)
	var alkaline: Color = NutrientPanel.ph_band_color(8.0)
	assert_eq(acid, NutrientPanel.PH_ACID_COLOR)
	assert_eq(optimal, NutrientPanel.BAR_OK)
	assert_eq(alkaline, NutrientPanel.PH_ALKALINE_COLOR)
	assert_ne(acid, alkaline, "acid and alkaline are not the same colour")


func test_ph_renders_per_layer() -> void:
	# AC #10: one pH value per layer, from the state.ph array.
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	add_child_autofree(panel)
	var layers: Array[Dictionary] = [
		{"depth_label": "0-25cm", "values": {"pH": 5.2}, "dominant_acceptor": "O2"},
		{"depth_label": "25-60cm", "values": {"pH": 7.9}, "dominant_acceptor": "O2"},
	]
	panel.show_layers(layers)
	assert_eq(panel._layer_bodies.size(), 2, "one body per layer")
	# The rendered value and its band colour, per layer — not just the row count.
	var top: Label = _ph_value_label(panel._layer_bodies[0], "5.2")
	var deep: Label = _ph_value_label(panel._layer_bodies[1], "7.9")
	assert_not_null(top, "layer 0 renders pH 5.2")
	assert_not_null(deep, "layer 1 renders pH 7.9")
	if top != null and deep != null:
		assert_eq(top.modulate, NutrientPanel.PH_ACID_COLOR, "5.2 shown in acid colour")
		assert_eq(deep.modulate, NutrientPanel.PH_ALKALINE_COLOR, "7.9 shown in alkaline colour")


func _ph_value_label(body: Node, text: String) -> Label:
	for node: Node in body.find_children("*", "Label", true, false):
		if (node as Label).text == text:
			return node as Label
	return null
