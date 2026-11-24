extends Node
## Capture scene for /visual-check (#631): the real farm view fed the measured
## grape Harvest reply, no backend. Run:
## godot --path game res://scenes/harvest_receipt_capture.tscn --write-movie out.png --quit-after 30

const FarmViewScene = preload("res://scenes/farm_view.tscn")

## The reply a grape Harvest on a 0.334 ha patch returns (default scenario, day 200).
const GRAPE_REPLY: Dictionary = {
	"status": "executed",
	"action": "harvest",
	"cost_credits": 50,
	"balance_credits": 10355,
	"date": "2024-10-18",
	"harvest_product": "fruit",
	"revenue_credits": 823,
	"profit_credits": 355,
	"settlements":
	[
		{
			"crop_key": "grape",
			"product": "fruit",
			"patch_indices": [1],
			"area_ha": 0.334,
			"dry_kg_ha": 708.1,
			"dry_matter_fraction": 0.2528,
			"sold_kg_ha": 2801.1,
			"sold_kg": 935.6,
			"quarter": 4,
			"base_credits_per_kg": 0.8,
			"seasonal_multiplier": 1.1,
			"price_credits_per_kg": 0.88,
			"revenue_credits": 823,
		}
	],
}

var view: Node3D = null


func _ready() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)
	view = FarmViewScene.instantiate()
	view._api_client = Node.new()
	add_child(view)
	view.add_child(view._api_client)
	view._on_harvest_complete.call_deferred(true, GRAPE_REPLY, "grape", "field_1", 1)
