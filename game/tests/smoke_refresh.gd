extends Node
## Client-smoke driver for the cutaway refresh path (#520). Loaded only as an
## autoload through the temporary override.cfg that client_smoke.sh writes, so
## no gameplay run ever loads it.
##
## The debug driver opens the cutaway once, which is a first build, so the
## smoke never reached SoilView.show_cutaway's refresh branch. Once the flow
## overlay exists, this presses View Soil again on the same tile: the identical
## refresh a player triggers. Its "[FLOW] tubes=" line is the smoke's second
## liveness line, so a press that never lands fails the smoke.

const SOIL_VIEW_BUTTON := "UILayer/BottomBar/BottomVBox/ActionBar/SoilViewButton"
## Seconds after the first build, so its fade-in tweens have run as in play.
const PRESS_DELAY := 1.0


func _ready() -> void:
	get_tree().node_added.connect(_on_node_added)


func _on_node_added(node: Node) -> void:
	if not (node is FlowOverlay):
		return
	get_tree().node_added.disconnect(_on_node_added)
	await get_tree().create_timer(PRESS_DELAY).timeout
	var button: Button = get_tree().current_scene.get_node(SOIL_VIEW_BUTTON)
	button.pressed.emit()
