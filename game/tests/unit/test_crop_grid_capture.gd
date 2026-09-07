extends GutTest

const GridCapture = preload("res://scripts/crop_grid_capture.gd")


func test_crops_and_cols_defined() -> void:
	assert_eq(GridCapture.CROPS.size(), 5, "5 crop types")
	assert_eq(GridCapture.COLS.size(), 6, "6 growth columns")


func test_cols_have_required_keys() -> void:
	for col: Dictionary in GridCapture.COLS:
		assert_true(col.has("label"), "Column has label")
		assert_true(col.has("stage"), "Column has stage")
		assert_true(col.has("lai"), "Column has lai")
		assert_true(col.has("grain"), "Column has grain")
		assert_true(col.has("dev"), "Column has development stage")
		assert_true(col.has("lai_peak"), "Column has season-peak LAI")


func test_layout_defined_for_every_crop() -> void:
	for crop: String in GridCapture.CROPS:
		assert_true(GridCapture.CROP_LAYOUT.has(crop), "Layout for %s" % crop)
		assert_true(GridCapture.CROP_HEIGHTS.has(crop), "Height for %s" % crop)


func test_cells_centred_on_origin() -> void:
	var last: int = GridCapture.COLS.size() - 1
	for crop: String in GridCapture.CROPS:
		var left: float = GridCapture.cell_x(crop, 0)
		var right: float = GridCapture.cell_x(crop, last)
		assert_almost_eq(left, -right, 0.001, "Row %s symmetric about x = 0" % crop)


func test_row_camera_frames_row() -> void:
	var viewport := Vector2(1920, 800)
	for row in range(GridCapture.CROPS.size()):
		var shot: Dictionary = GridCapture.row_camera(row, viewport)
		var cz: float = GridCapture.row_z(row)
		assert_almost_eq(shot["target"].z, cz, 0.001, "Aimed at the row")
		assert_gt(shot["pos"].z, cz, "Camera in front of the row")
		assert_gt(shot["pos"].y, shot["target"].y, "Camera looks slightly down")
	# Wider rows (bigger cells) need a camera further back.
	var wheat: Dictionary = GridCapture.row_camera(GridCapture.CROPS.find("spring_wheat"), viewport)
	var maize: Dictionary = GridCapture.row_camera(GridCapture.CROPS.find("maize"), viewport)
	var wheat_dist: float = wheat["pos"].z - wheat["target"].z
	var maize_dist: float = maize["pos"].z - maize["target"].z
	assert_gt(maize_dist, wheat_dist, "Maize row framed from further back")


func test_wind_strength_on_farm_view_scale() -> void:
	assert_almost_eq(GridCapture.wind_strength(0.0), 0.0, 1e-6, "Calm")
	assert_almost_eq(GridCapture.wind_strength(2.0), 0.25, 1e-6, "Light breeze")
	assert_almost_eq(GridCapture.wind_strength(20.0), 1.0, 1e-6, "Capped at a gale")
