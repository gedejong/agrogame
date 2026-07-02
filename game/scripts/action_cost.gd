class_name ActionCost
extends RefCounted
## Decision-support formatting for action cost preview (#318).
##
## Cost values themselves come from the backend /action/preview endpoint
## (the single source of truth == _compute_action_cost); this helper only
## turns a (cost, balance) pair into button labels, affordability and
## explanatory tooltips so an expensive click is never blind.


static func is_affordable(cost: int, balance: int) -> bool:
	"""True when the current balance covers the action's cost."""
	return balance >= cost


static func format_button_label(base_label: String, cost: int) -> String:
	"""Append the estimated cost to a button label, e.g. 'Irrigate (40cr)'."""
	return "%s (%dcr)" % [base_label, cost]


static func tooltip_text(action: String, cost: int, balance: int) -> String:
	"""Explanatory tooltip: cost when affordable, block reason when not."""
	var pretty: String = action.capitalize()
	if is_affordable(cost, balance):
		return "%s costs %d credits (balance: %d)." % [pretty, cost, balance]
	var short: int = cost - balance
	return (
		"%s costs %d credits — you only have %d (short %d). Not enough credits."
		% [pretty, cost, balance, short]
	)
