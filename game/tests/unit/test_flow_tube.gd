extends GutTest
## Tests for FlowTube glass-tube component.

const FlowTubeRef = preload("res://scripts/flow_tube.gd")


func test_create_returns_node() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	assert_not_null(tube)
	assert_gt(tube.get_child_count(), 0, "Should have mesh + particles children")


func test_zero_length_tube_no_crash() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3.ZERO,
				"end": Vector3.ZERO,
				"color": Color.RED,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	assert_not_null(tube)


func test_radius_scales_with_magnitude() -> void:
	var thin: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.3, 0),
				"color": Color.GREEN,
				"magnitude": 0.1,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(thin)
	var thick: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0.2, 0, 0),
				"end": Vector3(0.2, -0.3, 0),
				"color": Color.GREEN,
				"magnitude": 1.0,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(thick)
	# Find CylinderMesh children and compare radii
	var thin_r := _get_tube_radius(thin)
	var thick_r := _get_tube_radius(thick)
	assert_gt(thick_r, thin_r, "Higher magnitude should produce larger radius")


func test_label_created_when_text_provided() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
				"label_text": "Test Label",
			}
		)
	)
	add_child_autofree(tube)
	var has_label := false
	for child: Node in tube.get_children():
		if child is Label3D:
			has_label = true
	assert_true(has_label, "Should have a Label3D when label_text provided")


func test_no_label_when_empty() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	for child: Node in tube.get_children():
		assert_false(child is Label3D, "No Label3D without label_text")


func _get_tube_radius(tube: Node3D) -> float:
	for child: Node in tube.get_children():
		if child is MeshInstance3D:
			var mi: MeshInstance3D = child as MeshInstance3D
			if mi.mesh is CylinderMesh:
				return (mi.mesh as CylinderMesh).top_radius
	return 0.0
