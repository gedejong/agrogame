extends GutTest

const DensityCapture = preload("res://scripts/maize_density_capture.gd")


func test_densities_and_labels_aligned() -> void:
	assert_gt(DensityCapture.DENSITIES.size(), 0, "at least one density variant")
	assert_eq(
		DensityCapture.DENSITIES.size(),
		DensityCapture.LABELS.size(),
		"one label per density variant",
	)


func test_densities_are_positive_grids() -> void:
	for d: Vector2i in DensityCapture.DENSITIES:
		assert_gt(d.x, 0, "grid rows positive")
		assert_gt(d.y, 0, "grid plants-per-row positive")


func test_block_tiles_positive() -> void:
	assert_gt(DensityCapture.BLOCK_TILES, 0, "block tile count positive")
