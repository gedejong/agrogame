extends GutTest

const MaizeRenderer = preload("res://scripts/maize_renderer.gd")
const CropRenderer = preload("res://scripts/crop_renderer.gd")


func test_draw_leaves_creates_children() -> void:
	var node := Node2D.new()
	add_child_autofree(node)
	MaizeRenderer.draw_leaves(node, 0.0, 0, 1.0, 0.8)
	assert_true(node.get_child_count() > 0, "Should create leaf Line2D children")


func test_draw_leaves_zero_progress_empty() -> void:
	var node := Node2D.new()
	add_child_autofree(node)
	MaizeRenderer.draw_leaves(node, 0.0, 0, 1.0, 0.0)
	assert_eq(node.get_child_count(), 0, "No leaves at zero growth progress")
