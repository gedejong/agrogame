extends GutTest
## FlowOverlay refresh with surviving path tubes (#520). Split from
## test_flow_overlay.gd to stay within gdlint max-public-methods.

const FlowOverlayRef = preload("res://scripts/flow_overlay.gd")

const TEST_PROFILE: Array[Dictionary] = [
	{"depth_cm": 25, "texture": "sand", "saturation": 0.38},
	{"depth_cm": 35, "texture": "sand", "saturation": 0.37},
	{"depth_cm": 40, "texture": "sand", "saturation": 0.36},
]


func test_identical_refresh_keeps_path_tubes_without_tween_errors() -> void:
	# WaterInfiltrated builds a path tube. An identical refresh keeps every tube
	# and must not start an empty tween ("started with no Tweeners").
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	var events: Array = [
		{
			"event_type": "WaterInfiltrated",
			"module": "agrogame.soil.water.events",
			"data": {"layer_indices": [0], "amounts_mm": [5.0]},
		}
	]
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	var ids: Array[int] = []
	var path_tubes := 0
	for tube: FlowTube in overlay._tubes:
		ids.append(tube.get_instance_id())
		if tube._tube_mesh != null and tube._tube_mesh.mesh is ArrayMesh:
			path_tubes += 1
	assert_gt(path_tubes, 0, "WaterInfiltrated should build at least one path tube")
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	var ids_after: Array[int] = []
	for tube: FlowTube in overlay._tubes:
		ids_after.append(tube.get_instance_id())
	assert_eq(ids_after, ids, "Every tube survives an identical refresh")
	await wait_process_frames(3)
	assert_engine_error_count(0, "No 'started with no Tweeners' engine error")
