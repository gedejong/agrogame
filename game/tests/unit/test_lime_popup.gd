extends GutTest

const LimePopupScript = preload("res://scripts/lime_popup.gd")


func _popup() -> LimePopup:
	var popup := LimePopupScript.new() as LimePopup
	add_child_autofree(popup)
	return popup


func test_script_loads() -> void:
	assert_not_null(LimePopupScript, "LimePopup script loads")


func test_builds_one_item_per_rate_tier() -> void:
	var popup: LimePopup = _popup()
	assert_eq(popup.item_count, LimePicker.option_count(), "one item per t/ha tier")
	assert_string_contains(popup.get_item_text(0), "t/ha", "tiers are labelled in t/ha")


func test_affordability_greys_out_unaffordable_tiers() -> void:
	var popup: LimePopup = _popup()
	# 125 cr covers only the 1 t/ha tier.
	popup.apply_affordability(125)
	assert_false(popup.is_item_disabled(0), "cheapest tier stays selectable")
	assert_true(popup.is_item_disabled(popup.item_count - 1), "dearest tier greyed out")


func test_unknown_balance_leaves_all_tiers_selectable() -> void:
	var popup: LimePopup = _popup()
	popup.apply_affordability(-1)
	for idx in range(popup.item_count):
		assert_false(popup.is_item_disabled(idx), "tier %d selectable" % idx)


func test_rate_selected_carries_kg_ha_and_cost() -> void:
	var popup: LimePopup = _popup()
	watch_signals(popup)
	popup._on_id_pressed(0)
	assert_signal_emitted_with_parameters(popup, "rate_selected", [1000.0, 125])


func test_out_of_range_selection_emits_nothing() -> void:
	var popup: LimePopup = _popup()
	watch_signals(popup)
	popup._on_id_pressed(LimePicker.option_count())
	assert_signal_not_emitted(popup, "rate_selected")


func test_popup_under_positions_below_the_button() -> void:
	var popup: LimePopup = _popup()
	var button := Button.new()
	add_child_autofree(button)
	button.position = Vector2(40, 60)
	button.size = Vector2(80, 30)
	popup.popup_under(button)
	var rect := button.get_global_rect()
	assert_eq(popup.position.y, int(rect.end.y), "opens directly below the button")
	popup.hide()
