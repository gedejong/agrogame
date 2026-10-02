extends GutTest

const NutrientPanel = preload("res://scripts/nutrient_panel.gd")


func test_nutrient_bars_defined() -> void:
	for key: String in ["NO₃", "NH₄", "P", "Water", "pH", "Microbe", "MWD"]:
		assert_true(NutrientPanel.NUTRIENT_BARS.has(key), "Bar config for %s" % key)
	assert_false(NutrientPanel.NUTRIENT_BARS.has("SOM"), "Carbon is not a stress bar")


func test_biology_bars_defined() -> void:
	# #317: microbial N and fungal fraction per-layer bars.
	for key: String in ["MicrobeN", "Fungal"]:
		assert_true(NutrientPanel.NUTRIENT_BARS.has(key), "Bar config for %s" % key)
	assert_eq(NutrientPanel.NUTRIENT_BARS["Fungal"]["max"], 1.0, "Fungal frac max 1.0")


func test_biomass_row_renders() -> void:
	# #317: root vs stem biomass split rendered when biomass dict passed.
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	add_child_autofree(panel)
	var layers: Array[Dictionary] = [
		{"depth_label": "0-20cm", "values": {}, "dominant_acceptor": "O2"},
	]
	panel.show_layers(layers, {"root_g_m2": 120.0, "stem_g_m2": 80.0})
	assert_eq(panel._layer_bodies.size(), 1, "Layer body still built with biomass")


func test_biomass_row_stem_only_when_root_zero() -> void:
	# #330: engine reports root_g_m2 == 0, so the split renders stem-only
	# (no visibly-wrong "R 0" bar) until root biomass is wired through.
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	add_child_autofree(panel)
	var layers: Array[Dictionary] = [
		{"depth_label": "0-20cm", "values": {}, "dominant_acceptor": "O2"},
	]
	panel.show_layers(layers, {"root_g_m2": 0.0, "stem_g_m2": 80.0})
	assert_eq(panel._layer_bodies.size(), 1, "Layer body still built with stem-only biomass")


func test_nutrient_bars_have_icon() -> void:
	for key: String in NutrientPanel.NUTRIENT_BARS:
		var cfg: Dictionary = NutrientPanel.NUTRIENT_BARS[key]
		assert_true(cfg.has("icon"), "%s has icon path" % key)


func test_stress_color_optimal() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 30.0, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_OK, "Optimal = green")


func test_stress_color_deficient() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 0.5, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Very low = red")


func test_stress_color_marginal() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 3.0, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_MARGINAL, "Low = yellow")


func test_stress_color_ph_extreme() -> void:
	var c: Color = NutrientPanel._stress_color("pH", 3.5, 5.5, 7.5)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Extreme pH = red")


func test_stress_color_ph_optimal() -> void:
	var c: Color = NutrientPanel._stress_color("pH", 6.5, 5.5, 7.5)
	assert_eq(c, NutrientPanel.BAR_OK, "Optimal pH = green")


func test_format_acceptor_all_values() -> void:
	assert_eq(NutrientPanel._format_acceptor("O2"), "O\u2082")
	assert_eq(NutrientPanel._format_acceptor("NO3"), "NO\u2083\u207b")
	assert_eq(NutrientPanel._format_acceptor("Fe3+"), "Fe\u00b3\u207a")
	assert_eq(NutrientPanel._format_acceptor("CH4"), "CH\u2084")


func test_format_acceptor_unknown() -> void:
	assert_eq(NutrientPanel._format_acceptor("Mn4+"), "Mn4+", "Unknown returns as-is")


func test_mwd_bar_stress_color_good() -> void:
	var c: Color = NutrientPanel._stress_color("MWD", 1.8, 1.5, 2.5)
	assert_eq(c, NutrientPanel.BAR_OK, "Good MWD >1.5 = green")


func test_mwd_bar_stress_color_marginal() -> void:
	var c: Color = NutrientPanel._stress_color("MWD", 0.8, 1.5, 2.5)
	assert_eq(c, NutrientPanel.BAR_MARGINAL, "Moderate MWD 0.5-1.5 = yellow")


func test_mwd_bar_stress_color_degraded() -> void:
	var c: Color = NutrientPanel._stress_color("MWD", 0.3, 1.5, 2.5)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Degraded MWD <0.5 = red")


func test_accordion_only_first_layer_expanded() -> void:
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	add_child_autofree(panel)
	var layers: Array[Dictionary] = [
		{"depth_label": "0-20cm", "values": {}, "dominant_acceptor": "O2"},
		{"depth_label": "20-40cm", "values": {}, "dominant_acceptor": "O2"},
		{"depth_label": "40-60cm", "values": {}, "dominant_acceptor": "O2"},
	]
	panel.show_layers(layers)
	assert_eq(panel._layer_bodies.size(), 3, "3 layer bodies")
	assert_true(panel._layer_bodies[0].visible, "Layer 0 expanded")
	assert_false(panel._layer_bodies[1].visible, "Layer 1 collapsed")
	assert_false(panel._layer_bodies[2].visible, "Layer 2 collapsed")


func test_accordion_expand_all() -> void:
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	add_child_autofree(panel)
	var layers: Array[Dictionary] = [
		{"depth_label": "0-20cm", "values": {}, "dominant_acceptor": "O2"},
		{"depth_label": "20-40cm", "values": {}, "dominant_acceptor": "O2"},
	]
	panel.show_layers(layers)
	panel._on_expand_all()
	assert_true(panel._layer_bodies[0].visible, "All expanded")
	assert_true(panel._layer_bodies[1].visible, "All expanded")
	panel._on_expand_all()
	assert_false(panel._layer_bodies[0].visible, "All collapsed")
	assert_false(panel._layer_bodies[1].visible, "All collapsed")


func test_accordion_toggle_layer() -> void:
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	add_child_autofree(panel)
	var layers: Array[Dictionary] = [
		{"depth_label": "0-20cm", "values": {}, "dominant_acceptor": "O2"},
		{"depth_label": "20-40cm", "values": {}, "dominant_acceptor": "O2"},
	]
	panel.show_layers(layers)
	assert_false(panel._layer_bodies[1].visible, "Layer 1 starts collapsed")
	panel._on_layer_header(1)
	assert_true(panel._layer_bodies[1].visible, "Layer 1 expanded after click")
	panel._on_layer_header(1)
	assert_false(panel._layer_bodies[1].visible, "Layer 1 collapsed after 2nd click")


# --- Per-layer pH readout (#465) ------------------------------------------
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
