class_name CropPopup
extends PopupMenu
## Crop picker for the Plant action (#525).
##
## Labels each crop with its seed cost for the patch it would sow, previewed
## through ApiClient.preview_action, so the player sees the area-scaled charge
## before planting. farm_view supplies the params, so preview and plant agree.

## Crop keys, one item each in order; an item's id is its index.
var crops: Array[String] = []
## Bumped by each refresh; a reply to an earlier one (perhaps for another
## patch) is dropped rather than labelling this one.
var _generation: int = 0


func _init(crop_keys: Array[String]) -> void:
	crops = crop_keys
	for i in range(crops.size()):
		add_item(crops[i].capitalize(), i)


## Reset every item to its bare, selectable label, then queue one plant preview
## per crop, in order, with params `params_for.call(crop_key)`. Previews share
## ApiClient's FIFO queue (#523); with no game yet the items stay bare.
func refresh_costs(api: Node, game_id: String, params_for: Callable) -> void:
	_generation += 1
	for i in range(crops.size()):
		set_item_text(i, crops[i].capitalize())
		set_item_disabled(i, false)
		if not game_id.is_empty():
			var reply := _on_cost.bind(_generation, i)
			api.preview_action(game_id, "plant", params_for.call(crops[i]), reply)


## Label item `i` with a reply's cost, greyed out if unaffordable. A failed or
## stale reply leaves the item as it is. Touches no action button (#534).
func _on_cost(success: bool, data: Dictionary, generation: int, i: int) -> void:
	if not success or generation != _generation:
		return
	var cost: int = data.get("cost_credits", 0)
	var affordable: bool = data.get("affordable", true)
	set_item_text(i, ActionCost.format_button_label(crops[i].capitalize(), cost))
	set_item_disabled(i, not affordable)
