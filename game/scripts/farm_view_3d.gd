extends Node3D
## 3D farm view scaffold — Phase 0 of 2D→3D migration (ADR-007).
## Sets up Camera3D, lights, environment, and ground plane.
## UI CanvasLayer ported from 2D scene.

@onready var camera_rig: Node3D = $CameraRig
@onready var camera: Camera3D = $CameraRig/Camera3D
@onready var status_label: Label = $UILayer/StatusLabel


func _ready() -> void:
	status_label.text = "3D scaffold — Phase 0"
