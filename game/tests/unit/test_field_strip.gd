extends GutTest
## The field strip (#602, #472 C-d): one toggle card per field in layout order,
## reading the field's crop, stage and lowest Quick Status gauge (G3).

const SEP := FieldStrip.SEP


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


func test_water_32_under_nutrient_60_reads_water_32_and_healthy_reads_ok() -> void:
	var dry := _tile("f", "maize", "vegetative", {"water_ks": 0.32, "n_stress": 0.4})
	assert_eq(FieldStrip.attention_text([dry]), "Water 32")
	var healthy := _tile(
		"f",
		"maize",
		"vegetative",
		{"water_ks": 1.0, "growth_vs_potential": 0.95, "root_zone_water_fraction": 0.9}
	)
	assert_eq(FieldStrip.attention_text([healthy]), "OK")


func test_attention_is_the_lowest_gauge_over_the_fields_tiles() -> void:
	var low_n := _tile("f", "maize", "vegetative", {"water_ks": 0.8, "p_stress": 0.5})
	var low_water := _tile("f", "maize", "vegetative", {"water_ks": 0.65})
	assert_eq(FieldStrip.attention_text([low_water, low_n]), "Nutrients 50")
	var tie := _tile("f", "maize", "vegetative", {"water_ks": 0.5})
	assert_eq(FieldStrip.attention_text([low_n, tie]), "Water 50", "a tie goes to water")
	var dry_root := _tile("f", "", "", {"root_zone_water_fraction": 0.45})
	assert_eq(FieldStrip.attention_text([dry_root]), "Root zone 45")
	var slow := _tile("f", "maize", "maturity", {"growth_vs_potential": 0.04})
	assert_eq(FieldStrip.attention_text([slow]), "Growth 4")


func test_only_a_score_below_good_and_shown_counts() -> void:
	var at_good := _tile("f", "maize", "vegetative", {"water_ks": 0.7})
	assert_eq(FieldStrip.attention_text([at_good]), "OK", "70 is not below 70")
	var unsown := _tile("f", "maize", "planted", {"water_ks": 0.1, "n_stress": 0.9})
	assert_eq(FieldStrip.attention_text([unsown]), "OK", "not shown before emergence")
	assert_eq(FieldStrip.attention_text([]), "OK")


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
