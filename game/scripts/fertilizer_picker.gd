class_name FertilizerPicker
extends RefCounted
## Fertilizer-type picker options for the Fertilize action (issue #349).
##
## Turns a flat picker option id into the (type, amount_kg_ha) params the
## backend's `fertilize` action expects, and estimates its cost. The cost
## formula mirrors routes._compute_action_cost so the label shown before
## applying matches the eventual ledger deduction; per-kg prices mirror
## data/economy/prices.yaml input_costs.fertilizer_*.

## Fertilizer types offered, in display order. Backend maps each to a
## nutrient: urea/ammonium_nitrate → N, tsp → P.
const TYPES: Array[String] = ["urea", "ammonium_nitrate", "tsp"]
## Human-readable labels with the nutrient supplied, shown in the picker.
const LABELS := {
	"urea": "Urea (N)",
	"ammonium_nitrate": "Ammonium Nitrate (N)",
	"tsp": "TSP (P)",
}
## Per-kg product cost — mirrors prices.yaml input_costs.fertilizer_*.
const PRICE_PER_KG := {
	"urea": 1,
	"ammonium_nitrate": 1,
	"tsp": 2,
}
## Application-rate tiers (kg/ha) offered per type.
const AMOUNTS_KG_HA: Array[float] = [25.0, 50.0, 100.0]
## Flat labor charge per management action (prices.yaml labor_per_action).
const LABOR_PER_ACTION := 50


## Number of type × amount options the picker offers.
static func option_count() -> int:
	return TYPES.size() * AMOUNTS_KG_HA.size()


## Fertilizer type for a flat option id, or "" when out of range.
## Options are laid out type-major: id = type_idx * amounts + amount_idx.
static func type_for(option_id: int) -> String:
	if option_id < 0 or option_id >= option_count():
		return ""
	var type_idx: int = option_id / AMOUNTS_KG_HA.size()
	return TYPES[type_idx]


## Application rate (kg/ha) for a flat option id, or 0.0 when out of range.
static func amount_for(option_id: int) -> float:
	if option_id < 0 or option_id >= option_count():
		return 0.0
	var amount_idx: int = option_id % AMOUNTS_KG_HA.size()
	return AMOUNTS_KG_HA[amount_idx]


## execute_action params for an option, or {} when the id is out of range.
static func params_for(option_id: int) -> Dictionary:
	var fert_type: String = type_for(option_id)
	if fert_type.is_empty():
		return {}
	return {"type": fert_type, "amount_kg_ha": amount_for(option_id)}


## Estimated cost in credits — mirrors routes._compute_action_cost("fertilize").
static func cost_for(fert_type: String, amount_kg_ha: float) -> int:
	var per_kg: int = PRICE_PER_KG.get(fert_type, 1)
	return int(LABOR_PER_ACTION + per_kg * amount_kg_ha)


## Picker label, e.g. "Urea (N)  50 kg/ha — 100 cr". Empty when out of range.
static func label_for(option_id: int) -> String:
	var fert_type: String = type_for(option_id)
	if fert_type.is_empty():
		return ""
	var amount: float = amount_for(option_id)
	var cost: int = cost_for(fert_type, amount)
	var name: String = LABELS.get(fert_type, fert_type)
	return "%s  %d kg/ha — %d cr" % [name, int(amount), cost]


## True when a new type group begins at this option id (for menu separators).
static func starts_new_group(option_id: int) -> bool:
	return option_id > 0 and option_id % AMOUNTS_KG_HA.size() == 0
