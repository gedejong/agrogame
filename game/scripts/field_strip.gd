class_name FieldStrip
extends PanelContainer
## The field strip (#602, #472 C-d and G3): one toggle card per field, top-centre,
## in layout order. A card names its field's crop, its stage and its most
## pressing Quick Status gauge, so the farm can be read without clicking every
## band. Pressing a card asks the view to make that field active; the view's
## active field (ActiveField) decides which card is highlighted.
##
## The attention text reuses QuickStatusCard.compute_scores and GOOD_THRESHOLD,
## so the strip and the card agree on what needs attention (#472 G3).

## Emitted when the player presses `field_id`'s card.
signal field_pressed(field_id: String)

## Level with the Quick Status card's top (QuickStatusCard.ORIGIN.y), so the strip
## clears the StatusLabel above it (y 16-36 in farm_view.tscn).
const TOP := 40.0
const FONT_SIZE := 11
const SEP := " · "
## The active field's card border: the selected tile's glow (sel_color in
## soil_tile.gdshader), so the highlight reads as the same selection.
const ACTIVE_BORDER := Color(1.0, 0.85, 0.3)

var _cards: Array[Button] = []
var _ids: Array[String] = []
var _row := HBoxContainer.new()


func _init() -> void:
	name = "FieldStrip"
	var style := UiTheme.create_panel_style()
	style.set_content_margin_all(6)
	add_theme_stylebox_override("panel", style)
	UiTheme.add_blur_bg(self)
	_row.add_theme_constant_override("separation", 6)
	add_child(_row)
	# Top-centre: anchored on the viewport's middle, growing both ways.
	anchor_left = 0.5
	anchor_right = 0.5
	offset_top = TOP
	offset_bottom = TOP  # grows down to its minimum height
	grow_horizontal = Control.GROW_DIRECTION_BOTH


## One card per field of `fields` ([{field_id, patches}]), in order, with its
## text from `tile_data` and `active_id`'s card highlighted.
func lay_out(fields: Array, tile_data: Array, active_id: String) -> void:
	for card: Button in _cards:
		card.free()  # at once, so the row never holds two layouts' cards
	_cards.clear()
	_ids.clear()
	for field: Dictionary in fields:
		var field_id: String = field["field_id"]
		var card := Button.new()
		card.toggle_mode = true
		card.focus_mode = Control.FOCUS_NONE  # Esc and the keys stay the view's
		card.add_theme_font_size_override("font_size", FONT_SIZE)
		UiTheme.style_button(card)
		var lit := UiTheme.create_button_style("hover")
		lit.border_color = ACTIVE_BORDER
		lit.set_border_width_all(2)
		card.add_theme_stylebox_override("pressed", lit)
		card.add_theme_stylebox_override("hover_pressed", lit)
		card.pressed.connect(func() -> void: field_pressed.emit(field_id))
		_row.add_child(card)
		_cards.append(card)
		_ids.append(field_id)
	refresh(tile_data)
	highlight(active_id)


## Rewrite every card's text from the tiles laid out as its field.
func refresh(tile_data: Array) -> void:
	for i in range(_cards.size()):
		var tiles := tiles_of_field(_ids[i], tile_data)
		_cards[i].text = card_text(_ids[i], tiles)


## Press `field_id`'s card and release the others, without emitting field_pressed.
func highlight(field_id: String) -> void:
	for i in range(_cards.size()):
		_cards[i].set_pressed_no_signal(_ids[i] == field_id)


## The cards, in layout order.
func cards() -> Array[Button]:
	return _cards


## "Field 2 · maize" over "vegetative · Water 32": the field, its crop, its stage
## (left out on a bare field) and its attention.
static func card_text(field_id: String, tiles: Array) -> String:
	var status := attention_text(tiles)
	var stage := stage_text(tiles)
	if not stage.is_empty():
		status = stage + SEP + status
	return "%s%s%s\n%s" % [ActiveField.display_name(field_id), SEP, crop_text(tiles), status]


## The tiles of `tile_data` laid out as `field_id`, in tile order.
static func tiles_of_field(field_id: String, tile_data: Array) -> Array:
	return tile_data.filter(func(t: Dictionary) -> bool: return t.get("field_id", "") == field_id)


## The field's one crop ("spring wheat"), "mixed" when its tiles carry more than
## one crop (a bare patch beside a crop counts as one), or "bare" when none has one.
static func crop_text(tiles: Array) -> String:
	var crops := _distinct(tiles.map(func(t: Dictionary) -> String: return t.get("crop_key", "")))
	if crops.size() > 1:
		return "mixed"
	if crops.is_empty() or String(crops[0]).is_empty():
		return "bare"
	return String(crops[0]).replace("_", " ")


## The field's one engine stage ("grain fill"), "mixed" when its tiles differ, or
## "" on a bare field. A crop sown but not yet stepped is "planted", as on the card.
static func stage_text(tiles: Array) -> String:
	var stages := _distinct(tiles.map(func(t: Dictionary) -> String: return _stage_of(t)))
	if stages.size() > 1:
		return "mixed"
	return "" if stages.is_empty() else String(stages[0]).replace("_", " ")


static func _stage_of(tile: Dictionary) -> String:
	if String(tile.get("crop_key", "")).is_empty():
		return ""
	var stage: String = tile.get("crop_stage_name", "")
	return "planted" if stage.is_empty() else stage


## The lowest Quick Status gauge over `tiles` as "<gauge> <int>" ("Water 32") when
## it is below QuickStatusCard.GOOD_THRESHOLD, else "OK". A gauge that does not
## apply (NOT_SHOWN) is skipped, and a tie goes to the earlier gauge, as on the
## card, where a water and nutrient tie goes to water.
static func attention_text(tiles: Array) -> String:
	var scores: Array = tiles.map(
		func(t: Dictionary) -> Dictionary: return QuickStatusCard.compute_scores(t)
	)
	var worst_label := ""
	var worst := QuickStatusCard.GOOD_THRESHOLD
	for def: Dictionary in QuickStatusCard.GAUGE_DEFS:
		for tile_scores: Dictionary in scores:
			var score: float = tile_scores[def["key"]]
			if score >= 0.0 and score < worst:
				worst = score
				worst_label = def["label"]
	if worst_label.is_empty():
		return "OK"
	return "%s %d" % [worst_label, floori(worst + 1e-6)]  # the card's rounding


static func _distinct(values: Array) -> Array:
	var out: Array = []
	for value: Variant in values:
		if not out.has(value):
			out.append(value)
	return out
