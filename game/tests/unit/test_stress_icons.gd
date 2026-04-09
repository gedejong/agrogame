extends GutTest
## Tests for StressIcons — weather damage and nutrient deficiency icons.

const StressIconsRef = preload("res://scripts/stress_icons.gd")


func _make_mesh(pos := Vector3.ZERO) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.position = pos
	add_child_autofree(mesh)
	return mesh


func test_frost_event_creates_icon() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh(Vector3(1, 0, 1))
	var patches := {
		"f":
		[
			{
				"events":
				[{"event_type": "FrostDamageApplied", "module": "t", "data": {"severity": 0.5}}]
			}
		]
	}
	icons.update_from_patches(patches, [{"soil_type": "loam"}], [mesh], ["loam"])
	assert_gt(icons._icons.size(), 0, "Frost event should create icon")


func test_no_events_no_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	icons.update_from_patches({"f": [{"events": []}]}, [{"soil_type": "loam"}], [mesh], ["loam"])
	assert_eq(icons._icons.size(), 0, "No events = no icons")


func test_clear_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	var patches := {
		"f": [{"events": [{"event_type": "HeatDamageApplied", "module": "t", "data": {}}]}]
	}
	icons.update_from_patches(patches, [{"soil_type": "s"}], [mesh], ["s"])
	assert_gt(icons._icons.size(), 0)
	icons.clear_icons()
	assert_eq(icons._icons.size(), 0, "clear_icons empties dict")


func test_drought_from_water_stress() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	var patches := {
		"f":
		[
			{
				"events":
				[{"event_type": "WaterStressComputed", "module": "t", "data": {"stress": 0.3}}]
			}
		]
	}
	icons.update_from_patches(patches, [{"soil_type": "s"}], [mesh], ["s"])
	assert_gt(icons._icons.size(), 0, "Drought icon should appear")


func test_n_deficiency_from_nutrient_stress() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	var patches := {
		"f":
		[
			{
				"events":
				[
					{
						"event_type": "NutrientStressComputed",
						"module": "t",
						"data": {"nutrient": "N", "stress": 0.2},
					}
				]
			}
		]
	}
	icons.update_from_patches(patches, [{"soil_type": "s"}], [mesh], ["s"])
	assert_gt(icons._icons.size(), 0, "N deficiency icon should appear")


func test_no_stress_above_threshold() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	var patches := {
		"f":
		[
			{
				"events":
				[
					{"event_type": "WaterStressComputed", "module": "t", "data": {"stress": 0.8}},
					{
						"event_type": "NutrientStressComputed",
						"module": "t",
						"data": {"nutrient": "N", "stress": 0.9},
					},
				]
			}
		]
	}
	icons.update_from_patches(patches, [{"soil_type": "s"}], [mesh], ["s"])
	assert_eq(icons._icons.size(), 0, "No icon when stress above threshold")


func test_multiple_stresses_stack() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := _make_mesh()
	var patches := {
		"f":
		[
			{
				"events":
				[
					{"event_type": "FrostDamageApplied", "module": "t", "data": {"severity": 0.5}},
					{"event_type": "WaterStressComputed", "module": "t", "data": {"stress": 0.2}},
				]
			}
		]
	}
	icons.update_from_patches(patches, [{"soil_type": "s"}], [mesh], ["s"])
	assert_gt(icons._icons.size(), 0, "Multiple stresses should create icons")
