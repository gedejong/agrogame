extends GutTest
## The capture scene feeds the farm view the measured grape reply (#631 C8).

const CaptureScene = preload("res://scenes/harvest_receipt_capture.tscn")


func test_capture_scene_shows_the_grape_receipt_and_status_line() -> void:
	var cap: Node = CaptureScene.instantiate()
	add_child_autofree(cap)
	await get_tree().process_frame
	await get_tree().process_frame
	var receipt: HarvestReceipt = cap.view.get_node("UILayer/HarvestReceipt")
	assert_not_null(receipt)
	assert_string_contains(cap.view.status_label.text, "grape fruit")
	assert_string_contains(cap.view.status_label.text, "net 773")
	assert_false(cap.view.status_label.text.contains("g/m"))
