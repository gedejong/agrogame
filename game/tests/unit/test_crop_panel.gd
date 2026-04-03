extends GutTest

const CropPanel = preload("res://scripts/crop_panel.gd")


func test_create_returns_panel() -> void:
	var data := {"crop_key": "maize", "crop_stage_name": "vegetative", "lai": 3.0}
	var panel: PanelContainer = CropPanel.create(data)
	assert_not_null(panel, "Should return a PanelContainer")
	panel.queue_free()


func test_create_empty_returns_null() -> void:
	var data := {"crop_key": "", "crop_stage_name": ""}
	var panel: PanelContainer = CropPanel.create(data)
	assert_null(panel, "Should return null for empty crop data")


func test_create_with_stress() -> void:
	var data := {"crop_key": "maize", "crop_stage_name": "flowering", "stress": 1}
	var panel: PanelContainer = CropPanel.create(data)
	assert_not_null(panel, "Should create panel with stress indicator")
	panel.queue_free()
