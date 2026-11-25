extends GutTest
## The trimmed Soil Analysis panel (#647): each layer opens on its headline
## rows, Expand All shows the rest, both outlive a refresh, and the list
## scrolls past max_height. Split from test_nutrient_panel.gd, which is at
## gdlint's max-public-methods.

const NutrientPanel = preload("res://scripts/nutrient_panel.gd")
## The rows layer 0 opens on (#647), and all 14 behind Expand All, by label.
const HEADLINE := ["NO₃", "NH₄", "P", "C total", "Water", "pH"]
const ALL_ROWS := [
	"NO₃",
	"NH₄",
	"P",
	"C total",
	"Water",
	"pH",
	"Microbe",
	"MicrobeN",
	"Fungal",
	"Fe",
	"Zn",
	"Mn",
	"Eh",
	"MWD",
]


## Three layers, as the game builds them: with the biomass row, capped at
## `max_height` (0: uncapped).
func _panel(max_height: float = 0.0) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.set_script(NutrientPanel)
	panel.max_height = max_height
	add_child_autofree(panel)
	panel.show_layers(_layers(["0-20cm", "20-40cm", "40-60cm"]), {"stem_g_m2": 80.0})
	return panel


func _layers(labels: Array) -> Array[Dictionary]:
	var layers: Array[Dictionary] = []
	for label: String in labels:
		layers.append({"depth_label": label, "values": {}, "dominant_acceptor": "O2"})
	return layers


## The labels of layer `i`'s rows as shown, top down; [] while it is closed.
func _rows(panel: PanelContainer, i: int) -> Array:
	var body: VBoxContainer = panel._layer_bodies[i]
	if not body.visible:
		return []
	var out: Array = []
	var details: VBoxContainer = body.get_node("Details")
	var rows: Array = body.get_children() + details.get_children()
	for row: Node in rows:
		if row == details or (row.get_parent() == details and not details.visible):
			continue
		var line: Node = row.get_node("TotalRow") if row.name == "OrganicCarbonSummary" else row
		out.append((line.get_child(1) as Label).text)
	return out


func test_layer_0_opens_on_its_six_headline_rows() -> void:
	# #647: the rows the player's actions move, in the panel's order.
	var panel := _panel()
	assert_eq(_rows(panel, 0), HEADLINE, "NO₃, NH₄, P, organic C, Water, pH")
	assert_eq([_rows(panel, 1), _rows(panel, 2)], [[], []], "layers 1 and 2: headers only")
	var headers: Array = panel._layer_headers.map(func(b: Button) -> String: return b.text)
	assert_eq(headers, ["▾ 0-20cm", "▸ 20-40cm", "▸ 40-60cm"])
	var texts: Array = panel.find_children("*", "Button", true, false).map(
		func(b: Button) -> String: return b.text
	)
	assert_does_not_have(texts, "All", "no flow-filter row")
	assert_does_not_have(texts, "EYE", "no flow toggle")


func test_a_header_toggles_its_layers_six_rows() -> void:
	var panel := _panel()
	panel._on_layer_header(1)
	assert_eq(_rows(panel, 1), HEADLINE)
	assert_eq(panel._layer_headers[1].text, "▾ 20-40cm")
	panel._on_layer_header(1)
	assert_eq(_rows(panel, 1), [])
	assert_eq(panel._layer_headers[1].text, "▸ 20-40cm")
	panel._on_layer_header(0)
	assert_eq(_rows(panel, 0), [], "layer 0 closes too")


func test_expand_all_shows_all_fourteen_rows_then_collapses_every_layer() -> void:
	var panel := _panel()
	panel._on_expand_all()
	for i in range(3):
		assert_eq(_rows(panel, i), ALL_ROWS, "layer %d" % i)
	panel._on_expand_all()
	for i in range(3):
		assert_eq(_rows(panel, i), [], "layer %d collapsed, as on main" % i)


func test_open_layers_and_expand_all_outlive_a_rebuild() -> void:
	var panel := _panel()
	panel._on_layer_header(2)
	panel.show_layers(_layers(["a", "b", "c"]))
	assert_eq([_rows(panel, 0), _rows(panel, 1), _rows(panel, 2)], [HEADLINE, [], HEADLINE])
	panel._on_expand_all()
	panel.show_layers(_layers(["a", "b", "c"]))
	assert_eq([_rows(panel, 0), _rows(panel, 1), _rows(panel, 2)], [ALL_ROWS, ALL_ROWS, ALL_ROWS])


func test_the_default_is_short_and_expand_all_scrolls_past_max_height() -> void:
	# Main's default, layer 0 fully open, measured 498 px; the trim's cap is 340.
	var panel := _panel(622.0)
	assert_lt(panel.get_combined_minimum_size().y, 340.0, "default height")
	panel._on_expand_all()
	assert_lt(panel._scroll.custom_minimum_size.y, panel._list.get_combined_minimum_size().y)
	assert_almost_eq(panel.get_combined_minimum_size().y, 622.0, 0.5, "capped at max_height")
