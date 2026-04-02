extends SubViewportContainer
## 3D underground soil cross-section view (#114).
## Shows soil layers, water levels, root depth, and nutrient/SOM indicators.
## Rendered in a SubViewport overlaid on the farm view.

signal closed

## Layer texture colors by soil class (ADR-005)
const LAYER_COLORS := {
	"sand": Color(0.85, 0.78, 0.62),
	"sandy_loam": Color(0.78, 0.70, 0.55),
	"loam": Color(0.60, 0.50, 0.38),
	"clay_loam": Color(0.50, 0.42, 0.32),
	"clay": Color(0.40, 0.32, 0.25),
	"peat": Color(0.25, 0.20, 0.15),
}
const DEFAULT_LAYER_COLOR := Color(0.55, 0.45, 0.35)

## Cross-section dimensions (meters in 3D space)
const SECTION_WIDTH := 2.0
const SECTION_DEPTH := 0.5
const CM_TO_M := 0.01

## Nutrient overlay colors
const N_COLOR := Color(0.2, 0.7, 0.2, 0.6)
const P_COLOR := Color(0.6, 0.2, 0.7, 0.6)
const SOM_COLOR := Color(0.3, 0.2, 0.1, 0.5)
const WATER_COLOR := Color(0.3, 0.5, 0.9, 0.4)

var _layers: Array[MeshInstance3D] = []
var _water_planes: Array[MeshInstance3D] = []
var _n_bars: Array[MeshInstance3D] = []
var _p_bars: Array[MeshInstance3D] = []
var _som_bars: Array[MeshInstance3D] = []
var _root_line: MeshInstance3D
var _scene_root: Node3D


func _ready() -> void:
	_scene_root = $SubViewport/SceneRoot
	visible = false


func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if event is InputEventKey:
		var ke := event as InputEventKey
		if ke.pressed and ke.keycode == KEY_ESCAPE:
			hide_view()


func show_view(soil_state: Dictionary, soil_profile_layers: Array) -> void:
	_clear_scene()
	_build_layers(soil_profile_layers, soil_state)
	_build_water(soil_profile_layers, soil_state)
	_build_nutrients(soil_profile_layers, soil_state)
	_build_som(soil_profile_layers, soil_state)
	_build_root_indicator(soil_state)
	visible = true


func hide_view() -> void:
	visible = false
	closed.emit()


func _clear_scene() -> void:
	for child in _scene_root.get_children():
		if child is MeshInstance3D:
			child.queue_free()
	_layers.clear()
	_water_planes.clear()
	_n_bars.clear()
	_p_bars.clear()
	_som_bars.clear()


func _build_layers(profile_layers: Array, _soil_state: Dictionary) -> void:
	var y_offset := 0.0
	for layer: Dictionary in profile_layers:
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var depth_m: float = depth_cm * CM_TO_M
		var texture: String = layer.get("texture", "loam")

		var mesh := BoxMesh.new()
		mesh.size = Vector3(SECTION_WIDTH, depth_m, SECTION_DEPTH)

		var mat := StandardMaterial3D.new()
		mat.albedo_color = LAYER_COLORS.get(texture, DEFAULT_LAYER_COLOR)

		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		instance.material_override = mat
		instance.position = Vector3(0, -y_offset - depth_m / 2.0, 0)

		_scene_root.add_child(instance)
		_layers.append(instance)
		y_offset += depth_m


func _build_water(profile_layers: Array, soil_state: Dictionary) -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var y_offset := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var depth_m: float = depth_cm * CM_TO_M
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var sat: float = layer.get("saturation", 0.45)
		var fill: float = clampf(theta / sat, 0.0, 1.0) if sat > 0 else 0.0

		if fill > 0.01:
			var water_h: float = depth_m * fill
			var mesh := BoxMesh.new()
			mesh.size = Vector3(SECTION_WIDTH * 0.98, water_h, SECTION_DEPTH * 0.98)

			var mat := StandardMaterial3D.new()
			mat.albedo_color = WATER_COLOR
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA

			var instance := MeshInstance3D.new()
			instance.mesh = mesh
			instance.material_override = mat
			# Position at bottom of layer
			instance.position = Vector3(0, -y_offset - depth_m + water_h / 2.0, 0)
			_scene_root.add_child(instance)
			_water_planes.append(instance)

		y_offset += depth_m


func _build_nutrients(profile_layers: Array, soil_state: Dictionary) -> void:
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var y_offset := 0.0
	var bar_width := 0.08

	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var depth_m: float = depth_cm * CM_TO_M

		# N bar (left side)
		var no3: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var n_h: float = clampf(no3 / 5.0, 0.01, depth_m * 0.9)
		var n_mesh := BoxMesh.new()
		n_mesh.size = Vector3(bar_width, n_h, bar_width)
		var n_mat := StandardMaterial3D.new()
		n_mat.albedo_color = N_COLOR
		n_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		var n_inst := MeshInstance3D.new()
		n_inst.mesh = n_mesh
		n_inst.material_override = n_mat
		n_inst.position = Vector3(-SECTION_WIDTH / 2.0 - 0.15, -y_offset - depth_m / 2.0, 0)
		_scene_root.add_child(n_inst)
		_n_bars.append(n_inst)

		# P bar (right side)
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var p_h: float = clampf(p_val / 5.0, 0.01, depth_m * 0.9)
		var p_mesh := BoxMesh.new()
		p_mesh.size = Vector3(bar_width, p_h, bar_width)
		var p_mat := StandardMaterial3D.new()
		p_mat.albedo_color = P_COLOR
		p_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		var p_inst := MeshInstance3D.new()
		p_inst.mesh = p_mesh
		p_inst.material_override = p_mat
		p_inst.position = Vector3(SECTION_WIDTH / 2.0 + 0.15, -y_offset - depth_m / 2.0, 0)
		_scene_root.add_child(p_inst)
		_p_bars.append(p_inst)

		y_offset += depth_m


func _build_som(profile_layers: Array, soil_state: Dictionary) -> void:
	var labile: Array = soil_state.get("som_labile_c", [])
	var stable: Array = soil_state.get("som_stable_c", [])
	var y_offset := 0.0

	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 20.0)
		var depth_m: float = depth_cm * CM_TO_M

		var lab: float = labile[i] if i < labile.size() else 0.0
		var stab: float = stable[i] if i < stable.size() else 0.0
		var total: float = lab + stab
		# Normalize SOM density for visual thickness
		var som_frac: float = clampf(total / 50000.0, 0.0, 0.8)

		if som_frac > 0.01:
			var som_h: float = depth_m * 0.15
			var mesh := BoxMesh.new()
			mesh.size = Vector3(SECTION_WIDTH * som_frac, som_h, SECTION_DEPTH * 0.5)
			var mat := StandardMaterial3D.new()
			mat.albedo_color = SOM_COLOR
			mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			var instance := MeshInstance3D.new()
			instance.mesh = mesh
			instance.material_override = mat
			instance.position = Vector3(0, -y_offset - som_h / 2.0, SECTION_DEPTH * 0.3)
			_scene_root.add_child(instance)
			_som_bars.append(instance)

		y_offset += depth_m


func _build_root_indicator(soil_state: Dictionary) -> void:
	# Simple vertical line showing root depth
	var root_fracs: Array = soil_state.get("root_fraction", [])
	if root_fracs.is_empty():
		return
	# Find deepest layer with roots
	var max_depth := 0.0
	var cumulative := 0.0
	for i in range(root_fracs.size()):
		var frac: float = root_fracs[i]
		cumulative += 20.0  # approximate layer depth
		if frac > 0.01:
			max_depth = cumulative
	if max_depth <= 0.0:
		return

	var depth_m: float = max_depth * CM_TO_M
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.02
	mesh.bottom_radius = 0.005
	mesh.height = depth_m

	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.45, 0.35, 0.2)

	var instance := MeshInstance3D.new()
	instance.mesh = mesh
	instance.material_override = mat
	instance.position = Vector3(-0.3, -depth_m / 2.0, 0.1)
	_scene_root.add_child(instance)
	_root_line = instance
