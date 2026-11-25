extends Node
## Client-smoke driver for the soil panel refresh path (#520, #647). Loaded only
## as an autoload through the temporary override.cfg that client_smoke.sh
## writes, so no gameplay run ever loads it.
##
## The debug driver opens the Soil Analysis panel once, which is a first build.
## Once the panel exists, this presses Next Day: /step, then the slab update,
## then the panel's refresh in place, as a player gets them. That refresh's
## "[SOIL] panel" line is the smoke's second liveness line, so a press that
## never lands fails the smoke.

const PANEL_NAME := "SoilAnalysisPanel"
const NEXT_DAY_BUTTON := "UILayer/BottomBar/BottomVBox/ActionBar/NextDayButton"
## Seconds after the first build, so its first frames have run as in play.
const PRESS_DELAY := 1.0


func _ready() -> void:
	get_tree().node_added.connect(_on_node_added)


func _on_node_added(node: Node) -> void:
	if node.name != PANEL_NAME:
		return
	get_tree().node_added.disconnect(_on_node_added)
	await get_tree().create_timer(PRESS_DELAY).timeout
	var button: Button = get_tree().current_scene.get_node(NEXT_DAY_BUTTON)
	button.pressed.emit()
