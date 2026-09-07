extends GutTest

const Gen = preload("res://scripts/leaf_mask_generator.gd")


func _on(img: Image, x: int, y: int) -> bool:
	return img.get_pixel(x, y).r > 0.5


func _row_coverage(img: Image, y: int) -> float:
	var n := 0
	for x in range(img.get_width()):
		if _on(img, x, y):
			n += 1
	return float(n) / float(img.get_width())


func test_blade_mask_runs_along_x_with_pointed_tip() -> void:
	var img := Gen.build_blade_mask(Vector2i(128, 32), 0.1, 0.1, 1)
	assert_eq(img.get_width(), 128, "Width as requested")
	assert_true(_on(img, 0, 16), "Collar centre is opaque")
	assert_true(_on(img, 64, 16), "Mid-blade centre is opaque")
	assert_true(_on(img, 120, 16), "Tip centre stays opaque almost to the end")
	assert_false(_on(img, 127, 0), "Tip corner is cut away")
	assert_false(_on(img, 127, 31), "Tip corner is cut away")
	assert_gt(_row_coverage(img, 16), 0.98, "Midrib row is opaque along the blade")
	assert_lt(_row_coverage(img, 0), 0.9, "Margin row is frayed")
	assert_gt(_row_coverage(img, 0), 0.05, "Margin row keeps most of the blade edge")


func test_blade_mask_is_wider_than_the_legacy_lens() -> void:
	# Across the blade (y) the mask must keep nearly the full geometric width;
	# a lens-shaped mask would trim the edges everywhere.
	var img := Gen.build_blade_mask(Vector2i(256, 64), 0.06, 0.035, 1)
	var on := 0
	for y in range(64):
		if _on(img, 64, y):
			on += 1
	assert_gt(on, 56, "At a quarter of the length the blade is nearly full width")


func test_palmate_mask_has_lobes_and_petiolar_sinus() -> void:
	var img := Gen.build_palmate_mask(Vector2i(128, 128), 7)
	assert_true(_on(img, 64, 64), "Centre is opaque")
	assert_true(_on(img, 64, 118), "Apex lobe reaches towards the bottom edge")
	assert_false(_on(img, 64, 127), "Apex stays inside the texture")
	assert_false(_on(img, 64, 8), "Petiolar sinus notches the top")
	assert_true(_on(img, 64, 48), "Blade continues above the petiole")
	assert_true(_on(img, 16, 83), "Lateral lobes reach out below the horizontal")
	assert_true(_on(img, 111, 83), "Lateral lobes reach out below the horizontal")
	assert_false(_on(img, 12, 60), "Margin curves in between the lateral and basal lobes")
	assert_false(_on(img, 0, 0), "Corners are transparent")
	assert_false(_on(img, 127, 127), "Corners are transparent")


func test_palmate_mask_is_roughly_symmetric() -> void:
	var img := Gen.build_palmate_mask(Vector2i(64, 64), 7)
	var mismatches := 0
	for y in range(64):
		for x in range(32):
			if _on(img, x, y) != _on(img, 63 - x, y):
				mismatches += 1
	assert_lt(mismatches, 64, "Mirror halves differ only along the serrated margin")


func test_palmate_radius_peaks_at_apex_and_dips_at_petiole() -> void:
	var apex: float = Gen.palmate_radius(PI, 0.0)
	var petiole: float = Gen.palmate_radius(0.0, 0.0)
	var between: float = Gen.palmate_radius(0.45 * PI, 0.0)
	assert_gt(apex, between, "Apex lobe is the longest")
	assert_lt(petiole, between, "Sinus is the shortest radius")
