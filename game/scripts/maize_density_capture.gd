extends Node3D
## Dev tool: render blocks of maize tiles at several CROP_GRID densities
## side-by-side and screenshot them, to tune the in-game maize density.
## Renders left->right in increasing density, saves a PNG, then quits.
## Run: godot --path game res://scenes/maize_density_capture.tscn

const CropVisuals = preload("res://scripts/crop_visuals.gd")

const TILE_SIZE := 1.0
const METERS_PER_TILE := 2.0
const BLOCK_TILES := 4  # BLOCK_TILES x BLOCK_TILES tiles per density variant
const GAP := 1.5

# Before/after: current sparse density vs the chosen denser value.
const DENSITIES: Array[Vector2i] = [
	Vector2i(3, 8),  # 24 — current (too sparse)
	Vector2i(5, 12),  # 60 — chosen (lush, baked MultiMesh)
]
const LABELS: Array[String] = ["BEFORE  24/tile", "AFTER  60/tile"]

# Peak vegetative canopy (full green, pre-senescence).
const STAGE := 2
const LAI := 5.5
const GRAIN := 0.0

var _frame := 0
var _save_path := ""


func _ready() -> void:
	_save_path = OS.get_environment("HOME") + "/tmp/screenshots/maize_density.png"
	_build()
	_setup_camera()
	_setup_lighting()


func _build() -> void:
	var stride: float = BLOCK_TILES * TILE_SIZE + GAP
	for j in range(DENSITIES.size()):
		var grid := {"maize": DENSITIES[j]}
		for tx in range(BLOCK_TILES):
			for tz in range(BLOCK_TILES):
				var container := Node3D.new()
				container.position = Vector3(j * stride + tx * TILE_SIZE, 0.0, tz * TILE_SIZE)
				add_child(container)
				var tile_data := {
					"crop_key": "maize",
					"crop_stage": STAGE,
					"lai": LAI,
					"grain_g_m2": GRAIN,
					"col": tx,
					"row": tz,
				}
				CropVisuals.update_crop(tile_data, [container], grid, TILE_SIZE, METERS_PER_TILE)
				var ground := MeshInstance3D.new()
				var gm := PlaneMesh.new()
				gm.size = Vector2(TILE_SIZE, TILE_SIZE)
				ground.mesh = gm
				var mat := StandardMaterial3D.new()
				mat.albedo_color = Color(0.32, 0.22, 0.14)
				ground.material_override = mat
				ground.position = container.position + Vector3(0.0, -0.002, 0.0)
				add_child(ground)
		var label := Label3D.new()
		label.text = LABELS[j]
		label.font_size = 84
		label.modulate = Color(0.1, 0.1, 0.1)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		label.position = Vector3(
			j * stride + (BLOCK_TILES - 1) * TILE_SIZE * 0.5,
			2.7,
			(BLOCK_TILES - 1) * TILE_SIZE * 0.5
		)
		add_child(label)


func _setup_camera() -> void:
	var stride: float = BLOCK_TILES * TILE_SIZE + GAP
	var center_x: float = (
		(DENSITIES.size() - 1) * stride * 0.5 + (BLOCK_TILES - 1) * TILE_SIZE * 0.5
	)
	var center_z: float = (BLOCK_TILES - 1) * TILE_SIZE * 0.5
	var cam := Camera3D.new()
	cam.fov = 42.0
	cam.current = true
	cam.fov = 50.0
	add_child(cam)
	cam.position = Vector3(center_x, 8.0, center_z + 12.0)
	cam.look_at(Vector3(center_x, 0.5, center_z))


func _setup_lighting() -> void:
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-45.0, -35.0, 0.0)
	light.light_energy = 1.15
	light.shadow_enabled = true
	add_child(light)
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_color = Color(0.80, 0.85, 0.90)
	env.ambient_light_energy = 0.5
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.78, 0.85, 0.92)
	we.environment = env
	add_child(we)


func _process(_delta: float) -> void:
	_frame += 1
	if _frame == 6:
		var img: Image = get_viewport().get_texture().get_image()
		if img != null:
			var err: int = img.save_png(_save_path)
			print("maize_density save err=", err, " path=", _save_path)
		else:
			print("maize_density: null viewport image")
		get_tree().quit()
