extends GutTest
## DioramaArtefacts (#652, criterion 3): a deterministic placement in which
## corestones sit only in the Kenyan saprolite, gravel lenses only in the Dutch
## and Sahel sand, old roots only between the profile bottom and 2.0 m, and
## nothing above the profile bottom; and its data texture for the shader.

const K := DioramaArtefacts.Kind
## [climate key, profile bottom m]: the catalog's 100 cm (Kenya), 105 cm (the
## Dutch clay patch) and 110 cm (Sahel) sections, under a 4x slab.
const CASES := [["netherlands_temperate", 1.05], ["kenya_highlands", 1.0], ["sahel_arid", 1.1]]
const SPAN := Vector2(-6.0, 18.0)  # 12 wu of face, in m


func _place(key: String, bottom_m: float, seed_value: int = 652) -> Array[Dictionary]:
	return DioramaArtefacts.place(key, seed_value, bottom_m, bottom_m * 4.0, SPAN)


func _top(a: Dictionary) -> float:
	return a["d"] - a["half_h"]


func _bottom(a: Dictionary) -> float:
	return a["d"] + a["half_h"]


func _of(placed: Array[Dictionary], kind: int) -> Array[Dictionary]:
	return placed.filter(func(a: Dictionary) -> bool: return a["kind"] == kind)


func test_same_key_and_seed_give_the_same_list() -> void:
	for c: Array in CASES:
		assert_eq(_place(c[0], c[1]), _place(c[0], c[1]), c[0])
		assert_ne(_place(c[0], c[1], 1), _place(c[0], c[1], 2), "%s: the seed matters" % c[0])


func test_corestones_only_in_the_kenyan_saprolite() -> void:
	var stones := _of(_place("kenya_highlands", 1.0), K.CORESTONE)
	assert_gt(stones.size(), 3, "a scatter of corestones")
	for a: Dictionary in stones:
		assert_gte(_top(a), 2.6, "below the red clay")
		assert_lte(_bottom(a), 4.0, "above the slab bottom")
		assert_between(a["half_w"] * 2.0, 0.2, 0.8, "0.2 to 0.8 m across")
		assert_between(a["half_h"] / a["half_w"], 0.75, 1.0, "rounded")
	for c: Array in [CASES[0], CASES[2]]:
		assert_eq(_of(_place(c[0], c[1]), K.CORESTONE), [], c[0])


func test_lenses_only_in_the_dutch_and_sahel_sand() -> void:
	var hosts := {"netherlands_temperate": Vector2(2.8, 4.2), "sahel_arid": Vector2(1.1, 1.6)}
	for c: Array in [CASES[0], CASES[2]]:
		var lenses := _of(_place(c[0], c[1]), K.LENS)
		assert_gt(lenses.size(), 1, c[0])
		for a: Dictionary in lenses:
			assert_gte(_top(a), hosts[c[0]].x, "%s: inside the sand" % c[0])
			assert_lte(_bottom(a), hosts[c[0]].y, "%s: inside the sand" % c[0])
			assert_between(a["half_w"] * 2.0, 0.5, 2.0, "0.5 to 2 m long")
			assert_between(a["half_h"] * 2.0, 0.05, 0.2, "0.05 to 0.2 m thick")
	assert_eq(_of(_place("kenya_highlands", 1.0), K.LENS), [])


func test_old_roots_only_between_the_profile_bottom_and_two_metres() -> void:
	for c: Array in CASES:
		var roots := _of(_place(c[0], c[1]), K.ROOT)
		assert_gt(roots.size(), 10, "%s: sparse, one per 1.2 m or so" % c[0])
		for a: Dictionary in roots:
			assert_between(_top(a), c[1], c[1] + DioramaArtefacts.ROOT_START_M, c[0])
			assert_lte(_bottom(a), DioramaArtefacts.ROOT_FLOOR_M + 1e-6, c[0])
	assert_eq(_of(_place("kenya_highlands", 1.9), K.ROOT), [], "no room above 2.0 m")


func test_nothing_above_the_profile_bottom_or_outside_the_face() -> void:
	for c: Array in CASES:
		for a: Dictionary in _place(c[0], c[1]):
			assert_gte(_top(a), c[1], "%s kind %d" % [c[0], a["kind"]])
			assert_between(a["u"], SPAN.x, SPAN.y, c[0])
	assert_eq(_place("atlantis", 1.0), [], "an unknown key places nothing")


func test_bodies_do_not_overlap() -> void:
	for c: Array in CASES:
		var bodies := _of(_place(c[0], c[1]), K.CORESTONE) + _of(_place(c[0], c[1]), K.LENS)
		for i in range(bodies.size()):
			for j in range(i + 1, bodies.size()):
				var a: Dictionary = bodies[i]
				var b: Dictionary = bodies[j]
				var apart: bool = (
					absf(a["u"] - b["u"]) >= a["half_w"] + b["half_w"]
					or absf(a["d"] - b["d"]) >= a["half_h"] + b["half_h"]
				)
				assert_true(apart, "%s: %d and %d" % [c[0], i, j])


func test_texture_holds_one_column_per_artefact() -> void:
	var placed := _place("kenya_highlands", 1.0)
	var img := DioramaArtefacts.texture(placed).get_image()
	assert_eq(img.get_size(), Vector2i(placed.size(), 2))
	for i in range(placed.size()):
		var a: Dictionary = placed[i]
		var box := img.get_pixel(i, 0)
		var want := [a["u"], a["d"], a["half_w"], a["half_h"]]
		for c in range(4):
			assert_almost_eq(box[c], want[c], 1e-4, "box %d [%d]" % [i, c])
		assert_eq(img.get_pixel(i, 1).r, float(a["kind"]), "kind %d" % i)
		assert_almost_eq(img.get_pixel(i, 1).g, a["phase"], 1e-4, "phase %d" % i)
	var empty: Array[Dictionary] = []
	assert_eq(DioramaArtefacts.texture(empty).get_image().get_size(), Vector2i(1, 2))
