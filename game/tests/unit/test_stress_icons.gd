extends GutTest
## Tests for StressIcons — weather damage and nutrient deficiency icons.
## A tile's one threshold icon is the Quick Status card's advice (#669).

const StressIconsRef = preload("res://scripts/stress_icons.gd")
const QSC = preload("res://scripts/quick_status_card.gd")

## The #669 refinement's §5 cases: [id, tile keys over a vegetative maize
## tile, threshold_icon, compute_recommendation]. Stresses are 1 - factor.
const CASES: Array = [
	["I1", {"water_ks": 0.32, "n_stress": 0.4}, "drought", "Crop is short of water. Irrigate now."],
	[
		"I2",
		{"water_ks": 0.65},
		"drought",
		"Crop is starting to run short of water. Consider irrigating.",
	],
	[
		"I3",
		{"n_stress": 0.2},
		"n_deficiency",
		"Nitrogen is limiting growth. Apply urea or ammonium nitrate.",
	],
	["I4", {"crop_stage_name": "grain_fill", "n_stress": 0.2}, "", "No action needed."],
	["I5", {"s_stress": 0.48}, "s_deficiency", "Sulfur is limiting growth."],
	["I6", {"fe_stress": 0.31}, "fe_deficiency", "Iron is limiting growth."],
	["I7", {"zn_stress": 0.34}, "zn_deficiency", "Zinc is limiting growth."],
	["I8", {"mn_stress": 0.31}, "mn_deficiency", "Manganese is limiting growth."],
	["I9", {"p_stress": 0.5}, "p_deficiency", "Phosphorus is limiting growth. Apply TSP."],
	[
		"I10",
		{"water_ks": 0.45, "n_stress": 0.6},
		"n_deficiency",
		"Nitrogen is limiting growth. Apply urea or ammonium nitrate.",
	],
	[
		"I11",
		{"water_ks": 0.5, "p_stress": 0.5},
		"drought",
		"Crop is starting to run short of water. Consider irrigating.",
	],
	[
		"I12",
		{"crop_stage_name": "maturity", "water_ks": 0.1, "n_stress": 0.74},
		"",
		"Mature: ready to harvest.",
	],
	[
		"I13",
		{"root_zone_water_fraction": 0.40, "depletion_fraction_p": 0.55},
		"",
		"Root zone is drying. Irrigate before the crop shows stress.",
	],
	[
		"I14",
		{
			"growth_vs_potential": 0.04,
			"root_zone_water_fraction": 0.9,
			"depletion_fraction_p": 0.55,
		},
		"",
		"Growth is behind its potential after earlier stress or damage.",
	],
	["I15", {"crop_key": "", "crop_stage_name": ""}, "", "No crop planted. Consider planting."],
	["I16", {"crop_stage_name": "planted", "water_ks": 0.1}, "", "Sown, not yet emerged."],
	[
		"I17",
		{"crop_stage_name": "grain_fill", "n_stress": 0.71},
		"n_deficiency",
		"Nitrogen is limiting growth, but fertilizer this late adds little yield.",
	],
]


func _make_mesh(pos := Vector3.ZERO) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.position = pos
	add_child_autofree(mesh)
	return mesh


## A vegetative maize tile on field f's patch 0, with `extra` on top.
func _tile(extra: Dictionary) -> Dictionary:
	var tile := {
		"field_id": "f", "patch_idx": 0, "crop_key": "maize", "crop_stage_name": "vegetative"
	}
	tile.merge(extra, true)
	return tile


func _case(id: String) -> Dictionary:
	for c: Array in CASES:
		if c[0] == id:
			return _tile(c[1])
	return {}


## The icon keys update_from_patches draws on one tile, sorted; [] for none.
func _drawn(tile: Dictionary, events: Array = []) -> Array:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	icons.update_from_patches({"f": [{"events": events}]}, [tile], [_make_mesh()])
	if not icons._icons.has("0"):
		return []
	var keys: Array = icons._icons["0"].get_meta("stress_keys").duplicate()
	keys.sort()
	return keys


func test_threshold_icon_and_advice_follow_the_card() -> void:
	for c: Array in CASES:
		var tile := _tile(c[1])
		assert_eq(StressIconsRef.threshold_icon(tile), c[2], "%s icon" % c[0])
		assert_eq(QSC.compute_recommendation(tile), c[3], "%s advice" % c[0])
		var drawn: Array = [] if String(c[2]).is_empty() else [c[2]]
		assert_eq(_drawn(tile), drawn, "%s drawn" % c[0])


func test_drought_icon_if_and_only_if_the_card_advises_water() -> void:
	for c: Array in CASES:
		var tile := _tile(c[1])
		var water: bool = QSC.advised_gauge(tile) == "water"
		assert_eq(StressIconsRef.threshold_icon(tile) == "drought", water, c[0])


func test_every_icon_texture_exists() -> void:
	for table: Dictionary in [StressIconsRef.EVENT_STRESS, StressIconsRef.THRESHOLD_STRESS]:
		for key: String in table:
			var path: String = table[key]["texture"]
			assert_true(ResourceLoader.exists(path), "%s: %s" % [key, path])


func test_deficiency_icons_share_the_set_size() -> void:
	# 16 x 16 SVGs imported at svg/scale 4, like icon_n_deficiency.svg.
	var ref: Texture2D = load(StressIconsRef.THRESHOLD_STRESS["n_deficiency"]["texture"])
	for x: String in ["s", "fe", "zn", "mn"]:
		var tex: Texture2D = load(StressIconsRef.THRESHOLD_STRESS[x + "_deficiency"]["texture"])
		assert_eq(tex.get_size(), ref.get_size(), x)
	assert_eq(ref.get_width(), 64)


func test_s_deficiency_entry() -> void:
	var s: Dictionary = StressIconsRef.THRESHOLD_STRESS["s_deficiency"]
	assert_eq(s["label"], "S deficiency")
	assert_eq(s["color"], Color(0.90, 0.80, 0.20, 0.8), "sulfur yellow")


func test_frost_event_creates_icon() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh(Vector3(1, 0, 1))
	var patches := {
		"f":
		[
			{
				"events":
				[{"event_type": "FrostDamageApplied", "module": "t", "data": {"severity": 0.5}}]
			}
		]
	}
	icons.update_from_patches(patches, [{"field_id": "f", "patch_idx": 0}], [mesh])
	assert_gt(icons._icons.size(), 0, "Frost event should create icon")


func test_no_events_no_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	icons.update_from_patches({"f": [{"events": []}]}, [{"field_id": "f", "patch_idx": 0}], [mesh])
	assert_eq(icons._icons.size(), 0, "No events = no icons")


func test_clear_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	var patches := {
		"f": [{"events": [{"event_type": "HeatDamageApplied", "module": "t", "data": {}}]}]
	}
	icons.update_from_patches(patches, [{"field_id": "f", "patch_idx": 0}], [mesh])
	assert_gt(icons._icons.size(), 0)
	icons.clear_icons()
	assert_eq(icons._icons.size(), 0, "clear_icons empties dict")


func test_drought_icon_from_the_tiles_water_advice() -> void:
	# Was test_drought_from_water_stress (event Ks 0.3 < 0.5): the icon now
	# reads the tile the card reads, I1.
	assert_eq(_drawn(_case("I1")), ["drought"])


func test_n_deficiency_icon_from_the_tiles_nutrient_advice() -> void:
	# Was test_n_deficiency_from_nutrient_stress (N 0.2 < 0.5). I3: N 0.8,
	# above the old 0.5 but below the ADR-017 alert's 0.90, now draws.
	assert_eq(_drawn(_case("I3")), ["n_deficiency"])


func test_p_deficiency_icon_from_the_tiles_nutrient_advice() -> void:
	# Was test_p_deficiency_from_nutrient_stress (P 0.3 < 0.5); I9.
	assert_eq(_drawn(_case("I9")), ["p_deficiency"])


func test_no_icon_when_the_card_advises_nothing() -> void:
	# Was test_no_stress_above_threshold. The day's events no longer draw a
	# threshold icon: a healthy tile shows none, even beside a Ks 0.3 event.
	var events: Array = [
		{"event_type": "WaterStressComputed", "module": "t", "data": {"stress": 0.3}},
		{
			"event_type": "NutrientStressComputed",
			"module": "t",
			"data": {"nutrient": "N", "stress": 0.2}
		},
	]
	assert_eq(_drawn(_tile({"water_ks": 0.8, "n_stress": 0.05}), events), [])


func test_event_icons_stack_with_one_threshold_icon() -> void:
	# Was test_multiple_stresses_stack: frost and drought on one tile (I1).
	var frost := {"event_type": "FrostDamageApplied", "module": "t", "data": {"severity": 0.5}}
	assert_eq(_drawn(_case("I1"), [frost]), ["FrostDamageApplied", "drought"])
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	icons.update_from_patches({"f": [{"events": [frost]}]}, [_case("I1")], [_make_mesh()])
	var sprites := 0
	for child in icons._icons["0"].get_children():
		if child is Sprite3D:
			sprites += 1
	assert_eq(sprites, 2, "both icons draw a sprite")


func test_co_limitation_draws_only_the_advised_icon() -> void:
	# I10: Water 45 and Nutrients 40 are both marked; the advice is N.
	assert_eq(_drawn(_case("I10")), ["n_deficiency"])


func test_mature_crop_gets_no_icon_node() -> void:
	# I12: the Sahel N icon over the mature crop is gone.
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	icons.update_from_patches({"f": [{"events": []}]}, [_case("I12")], [_make_mesh()])
	assert_eq(icons._icons.size(), 0)


func test_icon_follows_the_advice_from_day_to_day() -> void:
	# The same tile over three updates: N, then water, then mature.
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var tile := _case("I3")
	var meshes: Array = [_make_mesh()]
	var drawn: Array = []
	for extra: Dictionary in [{}, {"water_ks": 0.3}, {"crop_stage_name": "maturity"}]:
		tile.merge(extra, true)
		icons.update_from_patches({"f": [{"events": []}]}, [tile], meshes)
		drawn.append(icons._icons["0"].get_meta("stress_keys") if icons._icons.has("0") else [])
	assert_eq(drawn, [["n_deficiency"], ["drought"], []])


func test_icons_map_to_tiles_by_patch_index() -> void:
	# Two patches on the same soil: only patch 1's tile gets patch 1's icon (#516).
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var frost := {"event_type": "FrostDamageApplied", "module": "t", "data": {}}
	var patches := {"field_1": [{"events": []}, {"events": [frost]}]}
	var tiles: Array = [
		{"field_id": "field_1", "patch_idx": 0, "soil_type": "organic"},
		{"field_id": "field_1", "patch_idx": 1, "soil_type": "organic"},
	]
	icons.update_from_patches(patches, tiles, [_make_mesh(), _make_mesh(Vector3.RIGHT)])
	assert_eq(icons._icons.keys(), ["1"], "icon on patch 1's tile only")


func test_harvested_bare_tile_shows_no_icon() -> void:
	# The day payload the API serves for a harvested patch since #542: no stage,
	# and only soil-side events (no frost, heat, water or nutrient stress).
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var bare := {
		"crop_key": "",
		"crop_stage": "",
		"events":
		[
			{"event_type": "RedoxChanged", "module": "t", "data": {"eh_mv": 450.0}},
			{
				"event_type": "EvapotranspirationComputed",
				"module": "t",
				"data": {"evaporation_mm": 3.5, "transpiration_mm": 0.0}
			},
			{
				"event_type": "PlantNUptakeComputed",
				"module": "t",
				"data": {"uptake_kg_ha": 0.0, "demand_kg_ha": 0.0}
			},
			{"event_type": "NutrientLeached", "module": "t", "data": {"nutrient": "NO3"}},
		]
	}
	icons.update_from_patches({"f": [bare]}, [{"field_id": "f", "patch_idx": 0}], [_make_mesh()])
	assert_eq(icons._icons.size(), 0, "a bare tile draws no stress icon")


func test_clear_tiles_drops_only_the_named_tiles_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var meshes: Array = [_make_mesh(), _make_mesh(Vector3(1, 0, 0))]
	var tiles: Array = [
		{"field_id": "f", "patch_idx": 0},
		{"field_id": "f", "patch_idx": 1},
	]
	var hit := {"events": [{"event_type": "HeatDamageApplied", "data": {}}]}
	icons.update_from_patches({"f": [hit, hit]}, tiles, meshes)
	assert_eq(icons._icons.keys().size(), 2)
	icons.clear_tiles([0] as Array[int])
	assert_eq(icons._icons.keys(), ["1"], "tile 1 keeps its icon")
	icons.clear_tiles([0] as Array[int])  # already gone: no error
	assert_eq(icons._icons.keys(), ["1"])
