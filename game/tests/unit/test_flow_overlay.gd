extends GutTest
## Tests for FlowOverlay tube network manager.

const FlowOverlayRef = preload("res://scripts/flow_overlay.gd")

const TEST_PROFILE: Array[Dictionary] = [
	{"depth_cm": 25, "texture": "sand", "saturation": 0.38},
	{"depth_cm": 35, "texture": "sand", "saturation": 0.37},
	{"depth_cm": 40, "texture": "sand", "saturation": 0.36},
]


func test_empty_events_no_tubes() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	overlay.update_from_events([], TEST_PROFILE, Vector3.ZERO)
	assert_eq(overlay._tubes.size(), 0, "No events = no tubes")


func test_water_infiltrated_creates_tube() -> void:
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
	assert_gt(overlay._tubes.size(), 0, "WaterInfiltrated should create a tube")


func test_zero_magnitude_no_tube() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	var events: Array = [
		{
			"event_type": "WaterInfiltrated",
			"module": "agrogame.soil.water.events",
			"data": {"layer_indices": [0], "amounts_mm": [0.0]},
		}
	]
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	assert_eq(overlay._tubes.size(), 0, "Zero magnitude = no tube")


func test_max_tubes_capped() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	# Create 30 events, should be capped at MAX_TUBES (20)
	var events: Array = []
	for i in range(30):
		(
			events
			. append(
				{
					"event_type": "NitrificationOccurred",
					"module": "agrogame.soil.nitrogen.events",
					"data": {"layer": 0, "amount_kg_ha": float(i + 1) * 0.1},
				}
			)
		)
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	assert_lte(overlay._tubes.size(), FlowOverlayRef.MAX_TUBES, "Capped at MAX_TUBES")


func test_clear_tubes() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	var events: Array = [
		{
			"event_type": "EvaporationTaken",
			"module": "agrogame.soil.water.events",
			"data": {"amount_mm": 2.0},
		}
	]
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	assert_gt(overlay._tubes.size(), 0)
	overlay.clear_tubes()
	assert_eq(overlay._tubes.size(), 0, "clear_tubes empties array")


func test_unknown_event_ignored() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	var events: Array = [
		{
			"event_type": "SomeUnknownEvent",
			"module": "test",
			"data": {"value": 42},
		}
	]
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	assert_eq(overlay._tubes.size(), 0, "Unknown events ignored")


func test_show_test_tubes() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	overlay.show_test_tubes()
	assert_gt(overlay._tubes.size(), 0, "Debug test should create sample tubes")


func test_update_reuses_matching_tubes() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	var events: Array = [
		{
			"event_type": "EvaporationTaken",
			"module": "agrogame.soil.water.events",
			"data": {"amount_mm": 2.0},
		}
	]
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	var first_count: int = overlay._tubes.size()
	assert_gt(first_count, 0)
	# Second update with same event type: should reuse tube (not double)
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	assert_eq(overlay._tubes.size(), first_count, "Should reuse matching tubes")


func test_rain_connector_added_for_heavy_rain() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	var events: Array = [
		{
			"event_type": "WaterInfiltrated",
			"module": "agrogame.soil.water.events",
			"data": {"layer_indices": [0], "amounts_mm": [8.0]},
		}
	]
	overlay.update_from_events(events, TEST_PROFILE, Vector3.ZERO)
	var labels: Array = []
	for tube in overlay._tubes:
		if tube is FlowTube and tube._label:
			labels.append(tube._label.text)
	assert_has(labels, "Rain", "Heavy rain should add Rain connector tube")
