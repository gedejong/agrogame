extends GutTest
## Tests for StressIcons — weather damage icons above tiles.

const StressIconsRef = preload("res://scripts/stress_icons.gd")


func test_frost_event_creates_icon() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := MeshInstance3D.new()
	mesh.position = Vector3(1, 0, 1)
	add_child_autofree(mesh)
	var patches := {
		"field_0":
		[
			{
				"events":
				[
					{
						"event_type": "FrostDamageApplied",
						"module": "test",
						"data": {"severity": 0.5},
					}
				]
			}
		]
	}
	var tile_data := [{"soil_type": "loam"}]
	var tile_meshes: Array[MeshInstance3D] = [mesh]
	var soil_types: Array[String] = ["loam"]
	icons.update_from_patches(patches, tile_data, tile_meshes, soil_types)
	assert_gt(icons._icons.size(), 0, "Frost event should create icon")


func test_no_events_no_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var patches := {"field_0": [{"events": []}]}
	var tile_data := [{"soil_type": "loam"}]
	var mesh := MeshInstance3D.new()
	add_child_autofree(mesh)
	var tile_meshes: Array[MeshInstance3D] = [mesh]
	icons.update_from_patches(patches, tile_data, tile_meshes, ["loam"])
	assert_eq(icons._icons.size(), 0, "No events = no icons")


func test_clear_icons() -> void:
	var icons := StressIconsRef.new()
	add_child_autofree(icons)
	var mesh := MeshInstance3D.new()
	mesh.position = Vector3.ZERO
	add_child_autofree(mesh)
	var patches := {
		"f": [{"events": [{"event_type": "HeatDamageApplied", "module": "t", "data": {}}]}]
	}
	icons.update_from_patches(patches, [{"soil_type": "s"}], [mesh], ["s"])
	assert_gt(icons._icons.size(), 0)
	icons.clear_icons()
	assert_eq(icons._icons.size(), 0, "clear_icons empties dict")
