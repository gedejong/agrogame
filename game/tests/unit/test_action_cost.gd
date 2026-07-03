extends GutTest
## Tests for ActionCost — action cost preview formatting helpers (#318).

const ActionCostScript = preload("res://scripts/action_cost.gd")


func test_is_affordable_true_when_balance_covers_cost() -> void:
	assert_true(ActionCostScript.is_affordable(40, 100), "40 <= 100 is affordable")
	assert_true(ActionCostScript.is_affordable(100, 100), "exact balance is affordable")


func test_is_affordable_false_when_cost_exceeds_balance() -> void:
	assert_false(ActionCostScript.is_affordable(120, 100), "120 > 100 not affordable")


func test_format_button_label_appends_cost() -> void:
	assert_eq(
		ActionCostScript.format_button_label("Irrigate", 40),
		"Irrigate (40cr)",
		"Label should show the estimated cost in credits",
	)


func test_format_button_label_from_price_marks_lower_bound() -> void:
	# Multi-tier actions (fertilizer picker, #349) show a "from" price so the
	# label does not read as a fixed cost.
	assert_eq(
		ActionCostScript.format_button_label("Fertilize", 75, true),
		"Fertilize (from 75cr)",
		"Variable-cost label shows a from-price",
	)


func test_tooltip_affordable_shows_cost_and_balance() -> void:
	var tip: String = ActionCostScript.tooltip_text("irrigate", 40, 100)
	assert_true(tip.contains("40"), "Tooltip mentions cost")
	assert_true(tip.contains("100"), "Tooltip mentions balance")
	assert_false(tip.contains("Not enough"), "Affordable tooltip has no block reason")


func test_tooltip_unaffordable_explains_block() -> void:
	var tip: String = ActionCostScript.tooltip_text("irrigate", 120, 100)
	assert_true(tip.contains("Not enough"), "Blocked tooltip explains the block")
	assert_true(tip.contains("20"), "Blocked tooltip shows the shortfall (120-100)")
