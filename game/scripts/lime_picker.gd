class_name LimePicker
extends RefCounted
## Lime-rate picker options for the Lime action (issue #465).
##
## Separate from FertilizerPicker because lime is an amendment, not a
## fertiliser: it supplies no limiting nutrient, is priced under
## input_costs.amendment_lime_per_kg rather than fertilizer_*, and is applied
## in t/ha rather than the 25/50/100 kg/ha fertiliser tiers. The cost formula
## mirrors routes._compute_action_cost("lime") so the label shown before
## applying matches the eventual ledger deduction.

## Application-rate tiers offered, in t/ha. A typical maintenance dressing is
## 1-2 t/ha; a full correction on a buffered clay runs to 5 t/ha or more.
const AMOUNTS_T_HA: Array[float] = [1.0, 2.5, 5.0]
## Per-kg cost of ground limestone — mirrors prices.yaml
## input_costs.amendment_lime_per_kg. Float on purpose: lime is the first
## input priced below 1 credit/kg, and an int here truncates it to zero.
const PRICE_PER_KG: float = 0.075
## Flat labor charge per management action (prices.yaml labor_per_action).
const LABOR_PER_ACTION: int = 50
## Soil layer liming targets — layer 0 is the topsoil the backend defaults to.
const TARGET_LAYER: int = 0


## Number of rate tiers the picker offers.
static func option_count() -> int:
	return AMOUNTS_T_HA.size()


## Application rate (t/ha) for an option id, or 0.0 when out of range.
static func amount_t_ha_for(option_id: int) -> float:
	if option_id < 0 or option_id >= option_count():
		return 0.0
	return AMOUNTS_T_HA[option_id]


## Application rate in kg/ha — the unit the backend action takes.
static func amount_kg_ha_for(option_id: int) -> float:
	return amount_t_ha_for(option_id) * 1000.0


## execute_action params for an option, or {} when the id is out of range.
static func params_for(option_id: int) -> Dictionary:
	var amount_kg_ha: float = amount_kg_ha_for(option_id)
	if amount_kg_ha <= 0.0:
		return {}
	return {"amount_kg_ha": amount_kg_ha, "layer": TARGET_LAYER}


## Estimated cost in credits — mirrors routes._compute_action_cost("lime").
## Keeps the per-kg price in float arithmetic and rounds only at the end, so a
## sub-1 credit/kg price is charged rather than truncated away.
static func cost_for(amount_kg_ha: float) -> int:
	if amount_kg_ha <= 0.0:
		return 0
	return int(round(float(LABOR_PER_ACTION) + PRICE_PER_KG * amount_kg_ha))


## Option id of the cheapest tier — the "from" price the Lime button previews
## and gates on, so the button only blocks when no tier is affordable.
static func cheapest_option_id() -> int:
	var best_id: int = 0
	var best_cost: int = cost_for(amount_kg_ha_for(0))
	for i in range(1, option_count()):
		var candidate: int = cost_for(amount_kg_ha_for(i))
		if candidate < best_cost:
			best_cost = candidate
			best_id = i
	return best_id


## True when balance covers this option's estimated cost. Out of range → false.
static func is_affordable(option_id: int, balance: int) -> bool:
	var amount_kg_ha: float = amount_kg_ha_for(option_id)
	if amount_kg_ha <= 0.0:
		return false
	return balance >= cost_for(amount_kg_ha)


## Picker label, e.g. "Lime  2.5 t/ha — 238 cr". Empty when out of range.
static func label_for(option_id: int) -> String:
	var amount_t_ha: float = amount_t_ha_for(option_id)
	if amount_t_ha <= 0.0:
		return ""
	var cost: int = cost_for(amount_t_ha * 1000.0)
	return "Lime  %.1f t/ha — %d cr" % [amount_t_ha, cost]
