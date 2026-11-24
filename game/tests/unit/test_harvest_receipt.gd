extends GutTest
## The harvest receipt (#631): text from a Harvest reply, one non-modal panel.

const MAIZE: Dictionary = {
	"crop_key": "maize",
	"product": "grain",
	"patch_indices": [1],
	"area_ha": 0.334,
	"dry_kg_ha": 3984.5,
	"dry_matter_fraction": 1.0,
	"sold_kg_ha": 3984.5,
	"sold_kg": 1330.8,
	"quarter": 4,
	"base_credits_per_kg": 0.22,
	"seasonal_multiplier": 1.2,
	"price_credits_per_kg": 0.264,
	"revenue_credits": 351,
}
const GRAPE: Dictionary = {
	"crop_key": "grape",
	"product": "fruit",
	"patch_indices": [1],
	"area_ha": 0.334,
	"dry_kg_ha": 708.1,
	"dry_matter_fraction": 0.2528,
	"sold_kg_ha": 2801.1,
	"sold_kg": 935.6,
	"quarter": 4,
	"base_credits_per_kg": 0.8,
	"seasonal_multiplier": 1.1,
	"price_credits_per_kg": 0.88,
	"revenue_credits": 823,
}


func _reply(settlements: Array, cost: int = 50) -> Dictionary:
	return {
		"status": "executed",
		"cost_credits": cost,
		"date": "2024-10-18",
		"settlements": settlements,
	}


func _text(lines: Array[String]) -> String:
	return "\n".join(lines)


func test_cereal_receipt_has_exact_values_and_no_fresh() -> void:
	var text := _text(HarvestReceipt.lines_for(_reply([MAIZE]), "field_1"))
	for expected: String in [
		"2024-10-18 (Q4)",
		"Maize · grain · Field 1 · 0.334 ha",
		"3.98 t/ha",
		"Sold 1331 kg",
		"0.22 × 1.20 (Q4) = 0.264 cr/kg",
		"Revenue 351 cr",
		"Harvest labour −50 cr",
		"Net 301 cr",
	]:
		assert_string_contains(text, expected)
	assert_false(text.contains("fresh"), "a cereal receipt never says fresh")
	assert_false(text.contains("Grade"), "no receipt shows a grade")


func test_fruit_receipt_shows_fresh_and_never_grain() -> void:
	var text := _text(HarvestReceipt.lines_for(_reply([GRAPE]), "field_1"))
	for expected: String in [
		"Grape · fruit",
		"0.71 t/ha dry → 2.80 t/ha fresh (25.3% dry matter)",
		"Sold 936 kg",
		"0.80 × 1.10 (Q4) = 0.880 cr/kg",
		"Revenue 823 cr",
		"Net 773 cr",
	]:
		assert_string_contains(text, expected)
	assert_false(text.to_lower().contains("grain"), "a grape receipt never says grain")


func test_names_the_field_it_came_from() -> void:
	var text := _text(HarvestReceipt.lines_for(_reply([MAIZE]), "field_2"))
	assert_string_contains(text, "Field 2")
	assert_false(text.contains("Field 1"))


func test_immature_harvest_is_zero_and_net_negative() -> void:
	var st: Dictionary = MAIZE.duplicate()
	st["dry_kg_ha"] = 0.0
	st["sold_kg_ha"] = 0.0
	st["sold_kg"] = 0.0
	st["revenue_credits"] = 0
	var text := _text(HarvestReceipt.lines_for(_reply([st]), "field_1"))
	assert_string_contains(text, "0.00 t/ha")
	assert_string_contains(text, "Revenue 0 cr")
	assert_string_contains(text, "Net −50 cr")


func test_two_settlements_make_two_blocks_and_one_net() -> void:
	var lines := HarvestReceipt.lines_for(_reply([MAIZE, GRAPE]), "field_1")
	var text := _text(lines)
	assert_eq(text.count("Revenue "), 2)
	assert_eq(text.count("Net "), 1)
	assert_string_contains(text, "Net 1124 cr")


func test_no_settlements_has_no_lines() -> void:
	assert_eq(HarvestReceipt.lines_for(_reply([]), "field_1").size(), 0)
	assert_eq(HarvestReceipt.lines_for({}, "field_1").size(), 0)


func test_show_in_builds_one_panel_above_the_bottom_bar() -> void:
	var layer := Control.new()
	add_child_autofree(layer)
	var bar := PanelContainer.new()
	bar.name = "BottomBar"
	bar.custom_minimum_size = Vector2(0, 90)
	layer.add_child(bar)
	var receipt := HarvestReceipt.show_in(layer, _reply([MAIZE]), "field_1")
	assert_not_null(receipt)
	assert_eq(receipt.offset_bottom, -(90.0 + 8.0), "bottom edge sits above the bar")
	assert_eq(receipt.anchor_right, 1.0, "anchored right")
	assert_eq(receipt.anchor_bottom, 1.0, "anchored bottom")
	assert_gt(receipt.get_child_count(), 1, "blur plus content")


func test_show_in_without_a_bar_uses_the_fallback_height() -> void:
	var layer := Control.new()
	add_child_autofree(layer)
	var receipt := HarvestReceipt.show_in(layer, _reply([MAIZE]), "field_1")
	assert_eq(receipt.offset_bottom, -(HarvestReceipt.FALLBACK_BAR_HEIGHT + 8.0))


func _receipts(layer: Node) -> int:
	var n := 0
	for child: Node in layer.get_children():
		if child is HarvestReceipt:
			n += 1
	return n


func test_second_harvest_replaces_the_first_and_carries_none_of_it() -> void:
	var layer := Control.new()
	add_child_autofree(layer)
	HarvestReceipt.show_in(layer, _reply([MAIZE]), "field_1")
	var second := HarvestReceipt.show_in(layer, _reply([GRAPE]), "field_2")
	assert_eq(_receipts(layer), 1, "only one receipt node exists")
	var text := ""
	for label: Label in second.find_children("*", "Label", true, false):
		text += label.text + "\n"
	assert_string_contains(text, "Grape")
	assert_string_contains(text, "Field 2")
	assert_false(text.contains("Maize"))
	assert_false(text.contains("Revenue 351"))


func test_no_op_reply_shows_none_and_clears_the_old_one() -> void:
	var layer := Control.new()
	add_child_autofree(layer)
	HarvestReceipt.show_in(layer, _reply([MAIZE]), "field_1")
	var none := HarvestReceipt.show_in(layer, {"status": "no-op", "settlements": []}, "field_1")
	assert_null(none)
	assert_eq(_receipts(layer), 0)


func test_close_button_removes_the_receipt() -> void:
	var layer := Control.new()
	add_child_autofree(layer)
	var receipt := HarvestReceipt.show_in(layer, _reply([MAIZE]), "field_1")
	var close: Button = receipt.find_child("CloseButton", true, false)
	assert_not_null(close)
	close.pressed.emit()
	assert_eq(_receipts(layer), 0)
