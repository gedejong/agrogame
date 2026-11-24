class_name HarvestReceipt
extends PanelContainer
## Non-modal receipt for one Harvest (#631): what was harvested, at what price,
## and what the player was paid. Built from the Harvest reply alone, whose
## `settlements[]` carry the very inputs `settle_season` was charged on
## (ADR-003: revenue = kg/ha x ha x base price x seasonal multiplier), so the
## price shown is the price paid. It sits bottom-right above the BottomBar and
## is replaced by the next Harvest or closed with its x.

## The verb for what happens to the harvested kg. One constant so storing
## (#473) can change the word in one place.
const SOLD_WORD: String = "Sold"
const NODE_NAME: String = "HarvestReceipt"
const WIDTH: float = 380.0
const MARGIN: float = 16.0
const FALLBACK_BAR_HEIGHT: float = 66.0

var _lines: Array[String] = []


## The receipt's text lines for a Harvest reply (empty without settlements).
static func lines_for(reply: Dictionary, field_id: String) -> Array[String]:
	var lines: Array[String] = []
	var settlements: Array = reply.get("settlements", [])
	if settlements.is_empty():
		return lines
	var cost: int = int(reply.get("cost_credits", 0))
	var revenue: int = 0
	lines.append("%s (Q%d)" % [reply.get("date", ""), int(settlements[0].get("quarter", 1))])
	for st: Dictionary in settlements:
		revenue += int(st.get("revenue_credits", 0))
		lines.append_array(_block(st, field_id))
	lines.append("Harvest labour %s cr" % _signed(-cost))
	lines.append("Net %s cr" % _signed(revenue - cost))
	return lines


static func _block(st: Dictionary, field_id: String) -> Array[String]:
	var dry_t_ha: float = float(st.get("dry_kg_ha", 0.0)) / 1000.0
	var dmf: float = float(st.get("dry_matter_fraction", 1.0))
	var block: Array[String] = []
	(
		block
		. append(
			(
				"%s · %s · %s · %.3f ha"
				% [
					str(st.get("crop_key", "")).capitalize(),
					st.get("product", ""),
					ActiveField.display_name(field_id),
					float(st.get("area_ha", 0.0)),
				]
			)
		)
	)
	if dmf < 1.0:
		block.append(
			(
				"%.2f t/ha dry → %.2f t/ha fresh (%.1f%% dry matter)"
				% [dry_t_ha, float(st.get("sold_kg_ha", 0.0)) / 1000.0, dmf * 100.0]
			)
		)
	else:
		block.append("%.2f t/ha" % dry_t_ha)
	block.append("%s %d kg" % [SOLD_WORD, roundi(float(st.get("sold_kg", 0.0)))])
	(
		block
		. append(
			(
				"%.2f × %.2f (Q%d) = %.3f cr/kg"
				% [
					float(st.get("base_credits_per_kg", 0.0)),
					float(st.get("seasonal_multiplier", 1.0)),
					int(st.get("quarter", 1)),
					float(st.get("price_credits_per_kg", 0.0)),
				]
			)
		)
	)
	block.append("Revenue %d cr" % int(st.get("revenue_credits", 0)))
	return block


## "−50" (U+2212) for a negative amount, the plain integer otherwise.
static func _signed(amount: int) -> String:
	return "−%d" % -amount if amount < 0 else "%d" % amount


## Replace any receipt on `layer` with one for `reply`; null (and none left)
## when the reply settled nothing. Sits above the layer's BottomBar when present.
static func show_in(layer: Node, reply: Dictionary, field_id: String) -> HarvestReceipt:
	var old: Node = layer.get_node_or_null(NODE_NAME)
	if old != null:
		layer.remove_child(old)
		old.queue_free()
	var lines := lines_for(reply, field_id)
	if lines.is_empty():
		return null
	var receipt := HarvestReceipt.new()
	receipt.name = NODE_NAME
	receipt._lines = lines
	var bar: Control = layer.get_node_or_null("BottomBar")
	var bar_h: float = bar.size.y if bar != null else FALLBACK_BAR_HEIGHT
	receipt.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	receipt.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	receipt.grow_vertical = Control.GROW_DIRECTION_BEGIN
	receipt.offset_right = -MARGIN
	receipt.offset_bottom = -(maxf(bar_h, FALLBACK_BAR_HEIGHT) + MARGIN * 0.5)
	layer.add_child(receipt)
	return receipt


func _ready() -> void:
	custom_minimum_size = Vector2(WIDTH, 0)
	add_theme_stylebox_override("panel", UiTheme.create_panel_style())
	UiTheme.add_blur_bg(self)
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 3)
	add_child(vbox)
	for i in range(_lines.size()):
		var line: String = _lines[i]
		var label := Label.new()
		label.text = line
		label.add_theme_font_size_override("font_size", 12)
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		UiTheme.style_label(label, _style_for(i, line))
		if i == 0:
			var row := HBoxContainer.new()
			label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(label)
			row.add_child(_close_button())
			vbox.add_child(row)
		else:
			if line.contains(" · ") and i > 1:
				vbox.add_child(HSeparator.new())
			vbox.add_child(label)


func _close_button() -> Button:
	var close := Button.new()
	close.name = "CloseButton"
	close.text = "×"
	UiTheme.style_button(close)
	close.pressed.connect(_on_close_pressed)
	return close


func _on_close_pressed() -> void:
	get_parent().remove_child(self)
	queue_free()


static func _style_for(index: int, line: String) -> String:
	if index == 0:
		return "header"
	if line.contains(" · ") or line.begins_with("Revenue") or line.begins_with("Net"):
		return "value"
	return "body"
