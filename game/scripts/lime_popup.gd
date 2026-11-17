class_name LimePopup
extends PopupMenu
## Rate picker for the Lime action (issue #465).
##
## Owns the t/ha tier menu so farm_view only has to open it and react to a
## choice. Options and prices come from LimePicker, which mirrors
## routes._compute_action_cost("lime"); unaffordable tiers are greyed out so a
## selection never previews one price then hits a backend 400 for another.

## Emitted when the player picks a rate. ``amount_kg_ha`` is the value the
## backend action takes; ``cost_credits`` is the previewed charge.
signal rate_selected(amount_kg_ha: float, cost_credits: int)


func _ready() -> void:
	for i in range(LimePicker.option_count()):
		add_item(LimePicker.label_for(i), i)
	id_pressed.connect(_on_id_pressed)


## Grey out tiers the current balance cannot cover. A negative balance means
## "not yet known" (before the first cost preview) and leaves all selectable.
func apply_affordability(balance_credits: int) -> void:
	for idx in range(item_count):
		if is_item_separator(idx):
			continue
		var option_id: int = get_item_id(idx)
		var affordable: bool = (
			balance_credits < 0 or LimePicker.is_affordable(option_id, balance_credits)
		)
		set_item_disabled(idx, not affordable)


## Open the menu directly below a button.
func popup_under(button: Button) -> void:
	var rect := button.get_global_rect()
	position = Vector2i(int(rect.position.x), int(rect.end.y))
	popup()


func _on_id_pressed(option_id: int) -> void:
	var params: Dictionary = LimePicker.params_for(option_id)
	if params.is_empty():
		return
	var amount_kg_ha: float = params["amount_kg_ha"]
	rate_selected.emit(amount_kg_ha, LimePicker.cost_for(amount_kg_ha))
