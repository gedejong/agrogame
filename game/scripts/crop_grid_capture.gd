extends Node3D
## Auto-screenshot: renders all crops at multiple growth stages in a grid.
## Saves to ~/Desktop/crop_grid.png on startup, then returns to preview.
##
## Grid layout: rows = crops (maize, wheat, sorghum, rice, grape)
##              cols = growth stages (LAI 0.5, 1.5, 3.0, 5.0, 6.0 + grain fill)
##
## Activated from crop_preview.gd via "Capture Grid" button.

const CropVisuals = preload("res://scripts/crop_visuals.gd")

const CROPS: Array[String] = ["maize", "spring_wheat", "sorghum", "rice", "grape"]

const COLS: Array[Dictionary] = [
	{"label": "LAI 0.5\nEmerged", "stage": 1, "lai": 0.5, "grain": 0.0},
	{"label": "LAI 2.0\nVegetative", "stage": 2, "lai": 2.0, "grain": 0.0},
	{"label": "LAI 4.0\nVegetative", "stage": 2, "lai": 4.0, "grain": 0.0},
	{"label": "LAI 5.5\nFlowering", "stage": 3, "lai": 5.5, "grain": 0.3},
	{"label": "LAI 4.0\nMaturity", "stage": 4, "lai": 4.0, "grain": 0.8},
	{"label": "LAI 2.0\nSenescent", "stage": 4, "lai": 2.0, "grain": 1.0},
]

const CELL_SIZE := 2.0
const PLANT_SPACING := 0.4

var _frame_count: int = 0
var _save_path: String = ""


func _ready() -> void:
	# Determine save path
	_save_path = OS.get_environment("HOME") + "/tmp/screenshots/crop_grid.png"
	_build_grid()
	_setup_camera()
	_setup_lighting()


func _setup_camera() -> void:
	var total_w: float = COLS.size() * CELL_SIZE
	var total_d: float = CROPS.size() * CELL_SIZE
	var center := Vector3(total_w * 0.5 - CELL_SIZE * 0.5, 0.0, -total_d * 0.5 + CELL_SIZE * 0.5)
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = maxf(total_w, total_d) * 0.7
	# Elevated oblique: look down at ~35° from front-right so all rows visible
	cam.position = center + Vector3(2.0, total_d * 0.6, total_d * 0.8)
	cam.look_at(center + Vector3(0, 0.5, 0))
	cam.current = true
	add_child(cam)


func _setup_lighting() -> void:
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, -20, 0)
	light.shadow_enabled = false
	add_child(light)
	var ambient := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_color = Color.WHITE
	env.ambient_light_energy = 0.5
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.85, 0.88, 0.90)
	ambient.environment = env
	add_child(ambient)


func _build_grid() -> void:
	for row in range(CROPS.size()):
		var crop_key: String = CROPS[row]
		for col in range(COLS.size()):
			var cfg: Dictionary = COLS[col]
			var stage: int = cfg["stage"]
			var lai: float = cfg["lai"]
			var grain: float = cfg["grain"]
			var lai_frac: float = clampf(lai / 6.0, 0.0, 1.0)
			var growth: float = CropVisuals._calc_growth(stage, lai_frac, grain)
			var sen: float = CropVisuals._calc_senescence(stage, lai, grain)
			var stresses := {"water": 0.0, "n": 0.0, "p": 0.0, "fe": 0.0, "zn": 0.0}
			# 3 plants per cell for variety
			var cx: float = col * CELL_SIZE
			var cy: float = 0.0
			var cz: float = -row * CELL_SIZE
			for pi in range(3):
				var plant := CropVisuals.create_3d_plant(
					crop_key, growth, sen, stresses, grain, row * 100 + col * 10 + pi
				)
				plant.position = Vector3(cx + (float(pi) - 1.0) * PLANT_SPACING, cy, cz)
				add_child(plant)
			# Ground tile per cell
			var ground := MeshInstance3D.new()
			var gm := PlaneMesh.new()
			gm.size = Vector2(CELL_SIZE * 0.9, CELL_SIZE * 0.9)
			ground.mesh = gm
			var mat := StandardMaterial3D.new()
			mat.albedo_color = Color(0.35, 0.25, 0.15)
			ground.material_override = mat
			ground.position = Vector3(cx, -0.001, cz)
			add_child(ground)


func _process(_delta: float) -> void:
	# Wait 3 frames for rendering to settle, then capture
	_frame_count += 1
	if _frame_count == 5:
		_capture_screenshot()


func _capture_screenshot() -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		push_warning("CropGridCapture: failed to get viewport image")
		return
	# Add text labels via a 2D overlay would require a SubViewport;
	# for simplicity just save the raw 3D render.
	var err: int = img.save_png(_save_path)
	if err == OK:
		print("Crop grid saved to: ", _save_path)
	else:
		push_warning("CropGridCapture: save failed with error %d" % err)
