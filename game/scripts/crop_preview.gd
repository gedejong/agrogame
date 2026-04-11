extends Node3D
## Debug crop preview: side-view of crops at adjustable growth stages.
## Activated via project setting agrogame/debug/crop_preview = true.
## Uses the same stage→growth/senescence pipeline as the real game.

const CropVisuals = preload("res://scripts/crop_visuals.gd")

const CROPS: Array[String] = ["maize", "spring_wheat", "sorghum", "rice", "grape"]

const STAGE_NAMES: Array[String] = ["None", "Emerged", "Vegetative", "Flowering", "Maturity"]

const SLIDER_DEFS: Array[Dictionary] = [
	{"key": "stage", "label": "Stage (0-4)", "min": 0.0, "max": 4.0, "step": 1.0, "default": 2.0},
	{"key": "lai", "label": "LAI", "min": 0.0, "max": 6.0, "step": 0.1, "default": 3.0},
	{"key": "grain", "label": "Grain frac", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
	{"key": "water", "label": "Water stress", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
	{"key": "n", "label": "N stress", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
	{"key": "p", "label": "P stress", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
	{"key": "fe", "label": "Fe stress", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
	{"key": "zn", "label": "Zn stress", "min": 0.0, "max": 1.0, "step": 0.01, "default": 0.0},
]

var _container: Node3D = null
var _camera: Camera3D = null
var _camera_pivot: Node3D = null
var _cam_distance: float = 3.5
var _cam_yaw: float = 0.0
var _cam_pitch: float = -15.0
var _cam_target: Vector3 = Vector3(0, 0.6, 0)
var _dragging: bool = false
var _ui: CanvasLayer = null
var _sliders: Dictionary = {}
var _crop_menu: OptionButton = null
var _label: Label = null
var _current_crop: String = "spring_wheat"
var _capture_queue: Array[Dictionary] = []
var _capture_wait: int = 0


func _ready() -> void:
	_setup_camera()
	_setup_ui()
	_container = Node3D.new()
	add_child(_container)
	# Ground plane
	var ground := MeshInstance3D.new()
	var ground_mesh := PlaneMesh.new()
	ground_mesh.size = Vector2(6, 4)
	ground.mesh = ground_mesh
	var ground_mat := StandardMaterial3D.new()
	ground_mat.albedo_color = Color(0.35, 0.25, 0.15)
	ground.material_override = ground_mat
	add_child(ground)
	# Light
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45, -30, 0)
	light.shadow_enabled = true
	add_child(light)
	var ambient := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_color = Color.WHITE
	env.ambient_light_energy = 0.4
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.4, 0.45, 0.55)
	ambient.environment = env
	add_child(ambient)
	_rebuild()


func _setup_camera() -> void:
	_camera_pivot = Node3D.new()
	_camera_pivot.position = _cam_target
	add_child(_camera_pivot)
	_camera = Camera3D.new()
	_camera.current = true
	_camera_pivot.add_child(_camera)
	_update_camera()


func _update_camera() -> void:
	_camera_pivot.rotation_degrees = Vector3(_cam_pitch, _cam_yaw, 0)
	_camera.position = Vector3(0, 0, _cam_distance)
	_camera.look_at(_camera_pivot.global_position)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb: InputEventMouseButton = event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_cam_distance = maxf(0.5, _cam_distance - 0.3)
			_update_camera()
		elif mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_cam_distance = minf(10.0, _cam_distance + 0.3)
			_update_camera()
		elif mb.button_index == MOUSE_BUTTON_MIDDLE or mb.button_index == MOUSE_BUTTON_RIGHT:
			_dragging = mb.pressed
	elif event is InputEventMouseMotion and _dragging:
		var mm: InputEventMouseMotion = event as InputEventMouseMotion
		_cam_yaw -= mm.relative.x * 0.3
		_cam_pitch = clampf(_cam_pitch - mm.relative.y * 0.3, -89.0, 89.0)
		_update_camera()
	elif event is InputEventPanGesture:
		var pan: InputEventPanGesture = event as InputEventPanGesture
		_cam_distance = clampf(_cam_distance + pan.delta.y * 0.3, 0.5, 10.0)
		_update_camera()
	elif event is InputEventMagnifyGesture:
		var mag: InputEventMagnifyGesture = event as InputEventMagnifyGesture
		_cam_distance = clampf(_cam_distance / mag.factor, 0.5, 10.0)
		_update_camera()


func _setup_ui() -> void:
	_ui = CanvasLayer.new()
	add_child(_ui)
	var panel := PanelContainer.new()
	panel.position = Vector2(10, 10)
	panel.size = Vector2(300, 0)
	_ui.add_child(panel)
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	panel.add_child(vbox)
	# Title
	var title := Label.new()
	title.text = "Crop Preview (Debug)"
	title.add_theme_font_size_override("font_size", 14)
	vbox.add_child(title)
	# Crop selector
	_crop_menu = OptionButton.new()
	for i in range(CROPS.size()):
		_crop_menu.add_item(CROPS[i], i)
	_crop_menu.selected = CROPS.find("spring_wheat")
	_crop_menu.item_selected.connect(_on_crop_changed)
	vbox.add_child(_crop_menu)
	# Sliders
	for def: Dictionary in SLIDER_DEFS:
		var row := HBoxContainer.new()
		var lbl := Label.new()
		lbl.text = def["label"]
		lbl.custom_minimum_size.x = 90
		lbl.add_theme_font_size_override("font_size", 11)
		row.add_child(lbl)
		var slider := HSlider.new()
		slider.min_value = def["min"]
		slider.max_value = def["max"]
		slider.step = def.get("step", 0.01)
		slider.value = def["default"]
		slider.custom_minimum_size.x = 140
		slider.value_changed.connect(_on_slider_changed)
		row.add_child(slider)
		var val_lbl := Label.new()
		val_lbl.text = _format_slider(def["key"], def["default"])
		val_lbl.custom_minimum_size.x = 60
		val_lbl.add_theme_font_size_override("font_size", 11)
		row.add_child(val_lbl)
		_sliders[def["key"]] = {"slider": slider, "label": val_lbl}
		vbox.add_child(row)
	# Capture grid button
	var capture_btn := Button.new()
	capture_btn.text = "Capture Grid (all crops × stages)"
	capture_btn.pressed.connect(_on_capture_grid)
	vbox.add_child(capture_btn)
	# Info label
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 10)
	_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	vbox.add_child(_label)


func _format_slider(key: String, val: float) -> String:
	if key == "stage":
		var idx: int = int(clampf(val, 0.0, 4.0))
		return "%d %s" % [idx, STAGE_NAMES[idx]]
	return "%.2f" % val


func _on_capture_grid() -> void:
	# Build queue of all crop × stage combos to capture
	_capture_queue.clear()
	var stages: Array[Dictionary] = [
		{"stage": 1, "lai": 0.5, "grain": 0.0, "suffix": "1_emerged"},
		{"stage": 2, "lai": 2.0, "grain": 0.0, "suffix": "2_veg_low"},
		{"stage": 2, "lai": 4.0, "grain": 0.0, "suffix": "3_veg_high"},
		{"stage": 3, "lai": 5.5, "grain": 0.3, "suffix": "4_flowering"},
		{"stage": 4, "lai": 4.0, "grain": 0.8, "suffix": "5_maturity"},
		{"stage": 4, "lai": 2.0, "grain": 1.0, "suffix": "6_senescent"},
	]
	for crop: String in CROPS:
		for s: Dictionary in stages:
			_capture_queue.append({"crop": crop, "stage": s})
	_label.text = "Capturing %d screenshots..." % _capture_queue.size()
	_capture_next()


func _capture_next() -> void:
	if _capture_queue.is_empty():
		_label.text = "Done! Saved to ~/tmp/screenshots/"
		return
	var item: Dictionary = _capture_queue[0]
	var crop: String = item["crop"]
	var s: Dictionary = item["stage"]
	# Set sliders to match
	_current_crop = crop
	_crop_menu.selected = CROPS.find(crop)
	_sliders["stage"]["slider"].value = s["stage"]
	_sliders["lai"]["slider"].value = s["lai"]
	_sliders["grain"]["slider"].value = s["grain"]
	_rebuild()
	# Wait frames for render, then capture
	_capture_wait = 3


func _process(_delta: float) -> void:
	if _capture_wait > 0:
		_capture_wait -= 1
		if _capture_wait == 0:
			_do_capture()


func _do_capture() -> void:
	var item: Dictionary = _capture_queue.pop_front()
	var crop: String = item["crop"]
	var s: Dictionary = item["stage"]
	var path: String = (
		OS.get_environment("HOME") + "/tmp/screenshots/%s_%s.png" % [crop, s["suffix"]]
	)
	var img: Image = get_viewport().get_texture().get_image()
	if img:
		img.save_png(path)
	var remaining: int = _capture_queue.size()
	_label.text = "Captured %s %s (%d left)" % [crop, s["suffix"], remaining]
	_capture_next()


func _on_crop_changed(idx: int) -> void:
	_current_crop = CROPS[idx]
	_rebuild()


func _on_slider_changed(_value: float) -> void:
	_rebuild()


func _rebuild() -> void:
	for child in _container.get_children():
		child.queue_free()
	var stage: int = int(_sliders["stage"]["slider"].value)
	var lai: float = _sliders["lai"]["slider"].value
	var grain_frac: float = _sliders["grain"]["slider"].value
	var lai_frac: float = clampf(lai / 6.0, 0.0, 1.0)
	# Use the same pipeline as CropVisuals
	var growth: float = CropVisuals._calc_growth(stage, lai_frac, grain_frac)
	var sen: float = CropVisuals._calc_senescence(stage, lai, grain_frac)
	var stresses := {
		"water": _sliders["water"]["slider"].value,
		"n": _sliders["n"]["slider"].value,
		"p": _sliders["p"]["slider"].value,
		"fe": _sliders["fe"]["slider"].value,
		"zn": _sliders["zn"]["slider"].value,
	}
	# Update value labels
	for key: String in _sliders:
		var s: Dictionary = _sliders[key]
		s["label"].text = _format_slider(key, s["slider"].value)
	# Create 5 plants at same stage but different seeds
	for i in range(5):
		var plant := CropVisuals.create_3d_plant(
			_current_crop, growth, sen, stresses, grain_frac, i * 17 + 42
		)
		plant.position = Vector3(float(i - 2) * 0.6, 0, 0)
		_container.add_child(plant)
	# Info text
	var stage_name: String = STAGE_NAMES[stage] if stage < STAGE_NAMES.size() else "?"
	var info := "%s — %s\n" % [_current_crop, stage_name]
	info += "growth=%.2f  sen=%.2f  grain=%.2f  LAI=%.1f" % [growth, sen, grain_frac, lai]
	var stress_parts: Array[String] = []
	for key: String in stresses:
		if stresses[key] > 0.01:
			stress_parts.append("%s=%.2f" % [key, stresses[key]])
	if not stress_parts.is_empty():
		info += "\nStress: " + ", ".join(stress_parts)
	_label.text = info
