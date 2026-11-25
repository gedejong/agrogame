class_name CropStatus
extends RefCounted
## What the Quick Status card says about a tile's crop (#630): the growth stage,
## the root depth, and the heat and frost damage taken since the crop was sown.
## Static helpers over a tile's data; the card only lays the text out.
##
## Stage names are the engine's own PhenologyStage (DSSAT/WOFOST lineage), and
## the tooltip gives each stage's BBCH range. BBCH: Meier, U. (ed.) 2018, Growth
## stages of mono- and dicotyledonous plants, BBCH Monograph, JKI,
## doi:10.5073/20180906-074619; cereals, maize and rice after Lancashire et al.
## 1991, Ann. Appl. Biol. 119: 561-601; grapevine after Lorenz et al. 1995,
## Aust. J. Grape Wine Res. 1: 100-103. The engine's thresholds fix the
## correspondence: emergence is BBCH 09, anthesis (DVS 1) is principal stage 6,
## and physiological maturity (DVS 2) is BBCH 87 (maize black layer, cereal hard
## dough) or BBCH 89 (grapevine, ripe for harvest). DVS is the WOFOST
## development stage (Van Diepen et al. 1989; Supit et al. 1994).
##
## Damage: a heat day is Tmax above the crop's threshold in flowering or grain
## fill (CanopyRuntime._check_heat_damage; DSSAT CERES heat stress on grain set,
## Hatfield & Prueger 2015). A frost day removes lai_loss of leaf area when Tmin
## is below the threshold (_check_frost_damage; DSSAT CERES frost kill).

const NO_VALUE := "—"
const HEAT_KEY := "HeatDamageApplied"
const FROST_KEY := "FrostDamageApplied"
const DVS_NOTE := "DVS 0 = sowing, 1 = flowering, 2 = maturity."

## Per engine stage: [cereal label, grape label, cereal BBCH, grape BBCH].
const STAGES := {
	"planted": ["Sown", "Before bud burst", "00–08", "00–08"],
	"emerged": ["Emerged", "Bud burst", "09", "09"],
	"vegetative": ["Vegetative", "Shoot growth", "10–59", "11–57"],
	"flowering": ["Flowering", "Flowering", "60–69", "60–69"],
	"grain_fill": ["Grain fill", "Berry growth", "71–85", "71–85"],
	"maturity": ["Mature — ready to harvest", "Ripe — ready to harvest", "87–89", "89"],
}


## The stage row: "<label> · DVS 1.62", a label alone at maturity or when no DVS
## is known yet, "Sown" for a crop not yet stepped, and "—" for a bare tile.
static func stage_text(stage_name: String, dev_stage: float, crop_key: String) -> String:
	if crop_key.is_empty():
		return NO_VALUE
	var name := "planted" if stage_name.is_empty() else stage_name
	if not STAGES.has(name):
		return stage_name.capitalize()
	var label: String = STAGES[name][_col(crop_key)]
	if name == "maturity" or dev_stage < 0.0:
		return label
	return "%s · DVS %.2f" % [label, dev_stage]


## The stage row's tooltip: the stage's BBCH range and the DVS scale.
static func stage_tooltip(stage_name: String, crop_key: String) -> String:
	var name := "planted" if stage_name.is_empty() else stage_name
	if crop_key.is_empty() or not STAGES.has(name):
		return DVS_NOTE
	var row: Array = STAGES[name]
	return "%s: BBCH %s. %s" % [row[_col(crop_key)], row[2 + _col(crop_key)], DVS_NOTE]


## "Roots 108 cm", or "Roots —" for a bare tile or a depth of zero.
static func root_text(root_depth_cm: float, crop_key: String) -> String:
	if crop_key.is_empty() or root_depth_cm <= 0.0:
		return "Roots " + NO_VALUE
	return "Roots %d cm" % roundi(root_depth_cm)


## The damage rows, each {"kind": "heat" or "frost", "text": ...}: only those
## with a count above 0, from the tile's tally since its crop was sown. They
## state what the model does and no more: days above the heat threshold in the
## stages where the check runs, and days below the frost threshold with the
## leaf area lost. A frost threshold above 0 C (rice 10, sorghum 2) is chilling,
## so that row says Cold. The thresholds are the events' own `threshold_c`; a
## missing one drops the clause, and no default is invented.
static func damage_lines(tile: Dictionary) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	var heat_days: int = tile.get("heat_days", 0)
	if heat_days > 0:
		var late := "berry growth" if tile.get("crop_key", "") == "grape" else "grain fill"
		var above := _clause("above", tile.get("heat_threshold"))
		(
			out
			. append(
				{
					"kind": "heat",
					"text": "Heat: %s%s during flowering or %s" % [_days(heat_days), above, late],
				}
			)
		)
	var frost_days: int = tile.get("frost_days", 0)
	if frost_days > 0:
		var limit: Variant = tile.get("frost_threshold")
		var word := "Cold" if limit != null and float(limit) > 0.0 else "Frost"
		var loss: float = tile.get("frost_lai", 0.0)
		(
			out
			. append(
				{
					"kind": "frost",
					"text":
					(
						"%s: %s%s, LAI −%.2f"
						% [word, _days(frost_days), _clause("below", limit), loss]
					),
				}
			)
		)
	return out


## Fold a step's daily_snapshots into each tile's damage tally, in order. Only
## the snapshots are read, never patches[...].events, since the last day is in
## both. A snapshot with no crop, or whose DVS falls below the tile's last, is a
## new crop (a replant or the season rollover: DVS 2.00 to 0.01), so the tally
## starts again.
static func tally_step(snapshots: Array, tile_data: Array) -> void:
	for snap: Dictionary in snapshots:
		var stage: String = snap.get("crop_stage", "")
		var dvs: float = float(snap.get("dev_stage", 0.0))
		for i: int in FarmLayout.tiles_of(
			snap.get("field_id", ""), snap.get("patch_idx", -1), tile_data
		):
			var tile: Dictionary = tile_data[i]
			if stage.is_empty() or dvs < float(tile.get("tally_dvs", -1.0)):
				reset_tally(tile)
			if stage.is_empty():
				continue
			tile["tally_dvs"] = dvs
			for evt: Dictionary in snap.get("events", []):
				_count(tile, evt.get("event_type", ""), evt.get("data", {}))


## Zero a tile's damage tally.
static func reset_tally(tile: Dictionary) -> void:
	tile["heat_days"] = 0
	tile["heat_threshold"] = null
	tile["frost_days"] = 0
	tile["frost_lai"] = 0.0
	tile["frost_threshold"] = null
	tile["tally_dvs"] = -1.0


static func _count(tile: Dictionary, event_type: String, data: Dictionary) -> void:
	if event_type == HEAT_KEY:
		tile["heat_days"] = int(tile.get("heat_days", 0)) + 1
		tile["heat_threshold"] = data.get("threshold_c")
	elif event_type == FROST_KEY:
		tile["frost_days"] = int(tile.get("frost_days", 0)) + 1
		tile["frost_lai"] = float(tile.get("frost_lai", 0.0)) + float(data.get("lai_loss", 0.0))
		tile["frost_threshold"] = data.get("threshold_c")


## " above 35 °C", or "" when the event carried no threshold. A whole number
## prints whole, else to 1 dp; a negative one uses the minus sign.
static func _clause(word: String, threshold: Variant) -> String:
	if threshold == null:
		return ""
	var t: float = float(threshold)
	var text := "%d" % roundi(t) if is_equal_approx(t, roundf(t)) else "%.1f" % t
	return " %s %s °C" % [word, text.replace("-", "−")]


static func _col(crop_key: String) -> int:
	return 1 if crop_key == "grape" else 0


static func _days(n: int) -> String:
	return "1 day" if n == 1 else "%d days" % n
