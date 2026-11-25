extends GutTest
## The field strip (#602, #472 C-d): one toggle card per field in layout order,
## reading the field's crop, stage and the gauge the Quick Status card advises on.

const SEP := FieldStrip.SEP

## The #602 amendment's A cases (2026-11-25): one vegetative maize tile unless the
## overrides say otherwise, its attention and the card's advice on it.
const _WATER_NOW := "Crop is short of water. Irrigate now."
const _WATER_SOON := "Crop is starting to run short of water. Consider irrigating."
const _UREA := "Nitrogen is limiting growth. Apply urea or ammonium nitrate."
const _NONE := "No action needed."
const _A_CASES: Array = [
	["A1", {"water_ks": 0.32, "n_stress": 0.4}, "Water 32", _WATER_NOW],
	[
		"A2",
		{
			"growth_vs_potential": 0.95,
			"root_zone_water_fraction": 0.9,
			"depletion_fraction_p": 0.55
		},
		"OK",
		_NONE,
	],
	["A3", {"n_stress": 0.2}, "Nutrients 80", _UREA],
	["A4", {"crop_stage_name": "grain_fill", "n_stress": 0.2}, "OK", _NONE],
	[
		"A5",
		{
			"water_ks": 0.96,
			"n_stress": 0.7,
			"growth_vs_potential": 0.05,
			"root_zone_water_fraction": 0.33,
			"depletion_fraction_p": 0.55,
		},
		"Nutrients 30",
		_UREA,
	],
	[
		"A6",
		{
			"growth_vs_potential": 0.04,
			"root_zone_water_fraction": 0.9,
			"depletion_fraction_p": 0.55
		},
		"OK",
		"Growth is behind its potential after earlier stress or damage.",
	],
	[
		"A7",
		{"root_zone_water_fraction": 0.40, "depletion_fraction_p": 0.55},
		"Root zone 40",
		"Root zone is drying. Irrigate before the crop shows stress.",
	],
	["A8", {"root_zone_water_fraction": 0.50, "depletion_fraction_p": 0.55}, "OK", _NONE],
	[
		"A9",
		{
			"crop_stage_name": "grain_fill",
			"water_ks": 0.46,
			"root_zone_water_fraction": 0.21,
			"depletion_fraction_p": 0.55,
		},
		"Water 46",
		_WATER_SOON,
	],
	[
		"A10",
		{
			"crop_stage_name": "maturity",
			"water_ks": 0.1,
			"growth_vs_potential": 0.45,
			"root_zone_water_fraction": 0.05,
			"depletion_fraction_p": 0.55,
		},
		"OK",
		"Mature: ready to harvest.",
	],
	[
		"A11",
		{"crop_key": "", "crop_stage_name": "", "root_zone_water_fraction": 0.45},
		"OK",
		"No crop planted. Consider planting.",
	],
	[
		"A12",
		{"crop_stage_name": "planted", "water_ks": 0.1, "n_stress": 0.9},
		"OK",
		"Sown, not yet emerged.",
	],
	["A13", {"water_ks": 0.70}, "OK", _NONE],
]


func _strip() -> FieldStrip:
	var strip := FieldStrip.new()
	add_child_autofree(strip)
	return strip


func _fields(ids: Array) -> Array:
	return ids.map(func(id: String) -> Dictionary: return {"field_id": id, "patches": [{}]})


## A tile of `field_id` growing `crop` at `stage`, healthy unless `extra` says not.
func _tile(field_id: String, crop: String, stage: String, extra: Dictionary = {}) -> Dictionary:
	var tile := {"field_id": field_id, "crop_key": crop, "crop_stage_name": stage}
	tile.merge(extra, true)
	return tile


func _texts(strip: FieldStrip) -> Array:
	return strip.cards().map(func(c: Button) -> String: return c.text)


func test_one_card_per_field_in_layout_order() -> void:
	var strip := _strip()
	strip.lay_out(_fields(["field_1"]), [], "field_1")
	assert_eq(_texts(strip), ["Field 1%sbare\nOK" % SEP])
	strip.lay_out(_fields(["field_1", "field_2"]), [], "field_1")
	var heads: Array = _texts(strip).map(func(t: String) -> String: return t.get_slice(SEP, 0))
	assert_eq(heads, ["Field 1", "Field 2"], "two cards, in layout order")
	strip.lay_out(_fields(["field_2", "field_1"]), [], "field_1")
	heads = _texts(strip).map(func(t: String) -> String: return t.get_slice(SEP, 0))
	assert_eq(heads, ["Field 2", "Field 1"], "the layout's order, not the ids'")
	assert_eq(strip.cards().map(func(c: Button) -> bool: return c.toggle_mode), [true, true])


func test_relaying_out_replaces_the_cards() -> void:
	var strip := _strip()
	strip.lay_out(_fields(["field_1", "field_2"]), [], "field_1")
	strip.lay_out(_fields(["field_1"]), [], "field_1")
	assert_eq(strip.cards().size(), 1)
	assert_eq(strip._row.get_child_count(), 1, "the old cards leave the row")


func test_each_card_reads_only_its_own_fields_tiles() -> void:
	var strip := _strip()
	var tiles := [
		_tile("field_1", "maize", "vegetative"),
		_tile("field_2", "spring_wheat", "grain_fill", {"water_ks": 0.32}),
		_tile("field_1", "maize", "vegetative"),
	]
	strip.lay_out(_fields(["field_1", "field_2"]), tiles, "field_1")
	assert_eq(
		_texts(strip),
		[
			"Field 1%smaize\nvegetative%sOK" % [SEP, SEP],
			"Field 2%sspring wheat\ngrain fill%sWater 32" % [SEP, SEP],
		]
	)
	tiles[0]["crop_key"] = "rice"
	strip.refresh(tiles)
	assert_string_contains(strip.cards()[0].text, "mixed", "a refresh rereads the tiles")


func test_crop_names_the_single_crop_or_says_mixed_or_bare() -> void:
	var maize := _tile("f", "maize", "vegetative")
	var wheat := _tile("f", "spring_wheat", "vegetative")
	var bare := _tile("f", "", "")
	assert_eq(FieldStrip.crop_text([maize, maize]), "maize")
	assert_eq(FieldStrip.crop_text([wheat]), "spring wheat")
	assert_eq(FieldStrip.crop_text([maize, wheat]), "mixed")
	assert_eq(FieldStrip.crop_text([bare, bare]), "bare")
	assert_eq(FieldStrip.crop_text([maize, bare]), "mixed", "a bare patch beside a crop")
	assert_eq(FieldStrip.crop_text([]), "bare")


func test_stage_names_the_single_stage_or_says_mixed() -> void:
	var veg := _tile("f", "maize", "vegetative")
	var fill := _tile("f", "maize", "grain_fill")
	var bare := _tile("f", "", "")
	assert_eq(FieldStrip.stage_text([veg, veg]), "vegetative")
	assert_eq(FieldStrip.stage_text([fill]), "grain fill")
	assert_eq(FieldStrip.stage_text([veg, fill]), "mixed")
	assert_eq(FieldStrip.stage_text([veg, bare]), "mixed")
	assert_eq(FieldStrip.stage_text([bare, bare]), "", "a bare field has no stage")
	assert_eq(FieldStrip.stage_text([_tile("f", "rice", "")]), "planted", "sown, not stepped")


func test_attention_names_the_gauge_the_cards_advice_acts_on() -> void:
	for case: Array in _A_CASES:
		var tile := _tile("f", "maize", "vegetative", case[1])
		assert_eq(FieldStrip.attention_text([tile]), case[2], "%s attention" % case[0])
		assert_eq(QuickStatusCard.compute_recommendation(tile), case[3], "%s advice" % case[0])
	var bare := _tile("f", "maize", "vegetative", _A_CASES[10][1])
	assert_eq(FieldStrip.card_text("field_1", [bare]), "Field 1%sbare\nOK" % SEP, "A11 card")


## Vegetative maize tiles for the B cases.
func _veg(extra: Dictionary) -> Dictionary:
	return _tile("f", "maize", "vegetative", extra)


func test_a_fields_attention_ranks_its_tiles_advice() -> void:
	var dry_root := {"root_zone_water_fraction": 0.10, "depletion_fraction_p": 0.55}
	var mature := {
		"crop_stage_name": "maturity",
		"root_zone_water_fraction": 0.05,
		"growth_vs_potential": 0.3,
		"depletion_fraction_p": 0.55,
	}
	var drying := {"root_zone_water_fraction": 0.30, "depletion_fraction_p": 0.55}
	var cases: Array = [
		["B1", [{"water_ks": 0.65}, {"water_ks": 0.8, "p_stress": 0.5}], "Nutrients 50"],
		["B2", [{"water_ks": 0.8, "p_stress": 0.5}, {"water_ks": 0.5}], "Water 50"],
		["B3", [dry_root, {"n_stress": 0.2}], "Nutrients 80"],
		["B4", [mature, {"water_ks": 0.6}], "Water 60"],
		["B5", [{"growth_vs_potential": 0.2}, drying], "Root zone 30"],
		["B6", [], "OK"],
	]
	for case: Array in cases:
		var tiles: Array = (case[1] as Array).map(_veg)
		assert_eq(FieldStrip.attention_text(tiles), case[2], case[0])


func test_card_text_leaves_the_stage_out_on_a_bare_field() -> void:
	var rice := _tile("f", "rice", "vegetative", {"water_ks": 0.32})
	assert_eq(
		FieldStrip.card_text("field_2", [rice]), "Field 2%srice\nvegetative%sWater 32" % [SEP, SEP]
	)
	assert_eq(FieldStrip.card_text("field_1", [_tile("f", "", "")]), "Field 1%sbare\nOK" % SEP)


func _pressed(strip: FieldStrip) -> Array:
	return strip.cards().map(func(c: Button) -> bool: return c.button_pressed)


func test_highlight_presses_one_card_and_emits_nothing() -> void:
	var strip := _strip()
	watch_signals(strip)
	strip.lay_out(_fields(["field_1", "field_2"]), [], "field_1")
	assert_eq(_pressed(strip), [true, false])
	strip.highlight("field_2")
	assert_eq(_pressed(strip), [false, true])
	assert_signal_not_emitted(strip, "field_pressed")


func test_pressing_a_card_asks_for_its_field() -> void:
	var strip := _strip()
	watch_signals(strip)
	strip.lay_out(_fields(["field_1", "field_2"]), [], "field_1")
	strip.cards()[1].pressed.emit()
	assert_signal_emitted_with_parameters(strip, "field_pressed", ["field_2"])


func test_it_sits_top_centre_below_the_status_line() -> void:
	var strip := _strip()
	assert_eq([strip.anchor_left, strip.anchor_right], [0.5, 0.5])
	assert_eq(strip.grow_horizontal, Control.GROW_DIRECTION_BOTH)
	assert_eq(strip.offset_top, QuickStatusCard.ORIGIN.y, "level with the Quick Status card")
	assert_eq(strip.cards().size(), 0, "no card before a layout")
	assert_eq(strip.name, "FieldStrip")
