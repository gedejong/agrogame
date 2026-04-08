extends GutTest
## Tests for FlowOverlay tube network manager.

const FlowOverlayRef = preload("res://scripts/flow_overlay.gd")
const SoilViewRef = preload("res://scripts/soil_view.gd")


func test_empty_events_no_tubes() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	overlay.update_from_events([], SoilViewRef.get_profile_layers("sandy"), Vector3.ZERO)
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
	overlay.update_from_events(events, SoilViewRef.get_profile_layers("sandy"), Vector3.ZERO)
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
	overlay.update_from_events(events, SoilViewRef.get_profile_layers("sandy"), Vector3.ZERO)
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
	overlay.update_from_events(events, SoilViewRef.get_profile_layers("sandy"), Vector3.ZERO)
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
	overlay.update_from_events(events, SoilViewRef.get_profile_layers("sandy"), Vector3.ZERO)
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
	overlay.update_from_events(events, SoilViewRef.get_profile_layers("sandy"), Vector3.ZERO)
	assert_eq(overlay._tubes.size(), 0, "Unknown events ignored")


func test_show_test_tubes() -> void:
	var overlay := FlowOverlayRef.new()
	add_child_autofree(overlay)
	overlay.show_test_tubes()
	assert_gt(overlay._tubes.size(), 0, "Debug test should create sample tubes")
