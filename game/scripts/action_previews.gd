class_name ActionPreviews
extends RefCounted
## The cost previews on the action bar (#318, #349, #523, moved out of
## farm_view.gd for #601). One refresh asks the backend what each priced action
## would cost on a field, one after another, and writes the answer onto that
## action's button: its label, its tooltip, and whether it can be afforded.

## Action buttons and the exact params their handlers send, so the previewed
## cost label matches the eventual ledger deduction (#318). Fertilize spans
## several priced tiers (#349), so it carries no fixed params: the preview
## resolves the cheapest tier at request time (see params_for) and its
## button shows a "from" price, gating only when no tier is affordable.
const ACTIONS: Array[Dictionary] = [
	{"action": "irrigate", "label": "Irrigate", "params": {"amount_mm": 20}},
	{"action": "fertilize", "label": "Fertilize", "params": {}, "variable_cost": true},
	{"action": "tillage", "label": "Tillage", "params": {"intensity": 0.8}},
	{"action": "lime", "label": "Lime", "params": {}, "variable_cost": true},
]

var _api: Node
var _buttons: Dictionary  # action -> its Button
var _on_balance: Callable  # (balance: int) -> void, told each previewed balance
var _bar_held: Callable  # () -> bool, true while a request holds the bar (#534)


func _init(api: Node, buttons: Dictionary, on_balance: Callable, bar_held: Callable) -> void:
	_api = api
	_buttons = buttons
	_on_balance = on_balance
	_bar_held = bar_held


## The button `action`'s cost shows on, or null for an action with none.
func button_for(action: String) -> Button:
	return _buttons.get(action)


## Preview every action on `field_id`, the first now and each next on the reply.
func refresh(game_id: String, field_id: String) -> void:
	_preview_at(0, game_id, field_id)


func _preview_at(i: int, game_id: String, field_id: String) -> void:
	if i < 0 or i >= ACTIONS.size():
		return
	var spec: Dictionary = ACTIONS[i]
	_api.preview_action(
		game_id,
		field_id,
		spec["action"],
		params_for(spec),
		func(success: bool, data: Dictionary) -> void: _on_cost(success, data, i, game_id, field_id)
	)


## Fertilize has no fixed tier: preview (and gate on) the cheapest option so
## the button only blocks when no tier is affordable (#349 review).
func params_for(spec: Dictionary) -> Dictionary:
	if spec["action"] == "fertilize":
		return FertilizerPicker.params_for(FertilizerPicker.cheapest_option_id())
	if spec["action"] == "lime":
		return LimePicker.params_for(LimePicker.cheapest_option_id())
	return spec["params"]


func _on_cost(success: bool, data: Dictionary, i: int, game_id: String, field_id: String) -> void:
	if success:
		_apply(i, data)
	# Chain the next preview (one shared HTTPRequest handles them sequentially).
	_preview_at(i + 1, game_id, field_id)


func _apply(i: int, data: Dictionary) -> void:
	var spec: Dictionary = ACTIONS[i]
	var btn: Button = button_for(spec["action"])
	if btn == null:
		return
	var cost: int = data.get("cost_credits", 0)
	var balance: int = data.get("balance_credits", 0)
	var affordable: bool = data.get("affordable", true)
	_on_balance.call(balance)
	var variable_cost: bool = spec.get("variable_cost", false)
	btn.text = ActionCost.format_button_label(spec["label"], cost, variable_cost)
	btn.tooltip_text = ActionCost.tooltip_text(spec["action"], cost, balance)
	btn.disabled = not affordable or _bar_held.call()
