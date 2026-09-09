extends Node3D
## Auto-screenshot: renders every crop at a series of development stages in a
## grid and saves one overview plus one close-up per crop row.
##
## Grid layout: rows = crops, short crops in front and tall crops at the back
##              cols = development stages from emergence to maturity
##
## Files land in ~/tmp/screenshots/<prefix>crop_grid[_<crop>].png; the prefix
## comes from the AGROGAME_CAPTURE_PREFIX environment variable (e.g. "before/").
## AGROGAME_CAPTURE_WIND sets a wind speed (m/s) blowing across the grid so
## the shader wind bend shows in the stills; without it the plants stand still.
## Run standalone: godot --path game res://scenes/crop_grid_capture.tscn --quit-after 60

const CropVisuals = preload("res://scripts/crop_visuals.gd")
const CR = preload("res://scripts/crop_renderer_3d.gd")

## Front to back, so no row hides the one behind it in the overview.
const CROPS: Array[String] = ["spring_wheat", "rice", "grape", "sorghum", "maize"]

## Tallest expected plant per crop (m); frames the per-row close-up camera.
const CROP_HEIGHTS := {
	"maize": 2.7,
	"spring_wheat": 1.0,
	"sorghum": 2.1,
	"rice": 1.1,
	"grape": 2.0,
}

## Per-crop cell footprint (m), in-row plant spacing (m) and plants per cell,
## close to field densities at a scale where individual plants still read.
const CROP_LAYOUT := {
	"maize": {"cell": 2.0, "spacing": 0.35, "count": 3},
	"spring_wheat": {"cell": 1.0, "spacing": 0.14, "count": 5},
	"sorghum": {"cell": 1.8, "spacing": 0.3, "count": 3},
	"rice": {"cell": 1.0, "spacing": 0.18, "count": 4},
	"grape": {"cell": 1.4, "spacing": 0.0, "count": 1},
}

## Development columns: stage index as in CropVisuals, WOFOST development
## stage, current LAI, season-peak LAI and grain mass (g/m2).
const COLS: Array[Dictionary] = [
	{
		"label": "Emerged\nDVS 0.12\nLAI 0.3",
		"stage": 1,
		"dev": 0.12,
		"lai": 0.3,
		"lai_peak": 0.3,
		"grain": 0.0,
	},
	{
		"label": "Vegetative\nDVS 0.45\nLAI 1.5",
		"stage": 2,
		"dev": 0.45,
		"lai": 1.5,
		"lai_peak": 1.5,
		"grain": 0.0,
	},
	{
		"label": "Late vegetative\nDVS 0.85\nLAI 4.0",
		"stage": 2,
		"dev": 0.85,
		"lai": 4.0,
		"lai_peak": 4.0,
		"grain": 0.0,
	},
	{
		"label": "Flowering\nDVS 1.05\nLAI 4.5",
		"stage": 3,
		"dev": 1.05,
		"lai": 4.5,
		"lai_peak": 4.5,
		"grain": 0.0,
	},
	{
		"label": "Grain fill\nDVS 1.5\nLAI 3.5",
		"stage": 4,
		"dev": 1.5,
		"lai": 3.5,
		"lai_peak": 4.5,
		"grain": 400.0,
	},
	{
		"label": "Maturity\nDVS 2.0\nLAI 1.5",
		"stage": 4,
		"dev": 2.0,
		"lai": 1.5,
		"lai_peak": 4.5,
		"grain": 600.0,
	},
]

const ROW_PITCH := 2.4
## Label3D pixel size per metre of cell width.
const LABEL_SIZE_PER_M := 0.0028
## Vertical field of view (deg) of the capture camera.
const CAMERA_FOV := 40.0
## Frames to let rendering settle after each camera move before capturing.
const SETTLE_FRAMES := 4
## Wind speed (m/s) that maps to full shader wind strength, the farm view's scale.
const WIND_SCALE_MAX_MS := 8.0
## The capture wind blows diagonally across the grid.
const WIND_DIR := Vector2(0.7, 0.7)

var _shots: Array[Dictionary] = []
var _shot_idx: int = -1
var _frames_since_move: int = 0
var _camera: Camera3D
var _rows: Array[Node3D] = []
var _col_labels: Array[Node3D] = []


func _ready() -> void:
	var prefix: String = OS.get_environment("AGROGAME_CAPTURE_PREFIX")
	var base: String = OS.get_environment("HOME") + "/tmp/screenshots/" + prefix
	_build_grid()
	var wind_ms: float = OS.get_environment("AGROGAME_CAPTURE_WIND").to_float()
	if wind_ms > 0.0:
		CR.set_wind(self, wind_strength(wind_ms), WIND_DIR.normalized())
	_camera = Camera3D.new()
	_camera.fov = CAMERA_FOV
	_camera.current = true
	add_child(_camera)
	_setup_lighting()
	(
		_shots
		. append(
			{
				"path": base + "crop_grid.png",
				"row": -1,
				"pos": Vector3(0.0, 7.0, 6.5),
				"target": Vector3(0.0, 0.3, -5.0),
			}
		)
	)
	var viewport_size: Vector2 = get_viewport().get_visible_rect().size
	for row in range(CROPS.size()):
		var shot: Dictionary = row_camera(row, viewport_size)
		shot["path"] = base + "crop_grid_%s.png" % CROPS[row]
		shot["row"] = row
		_shots.append(shot)


static func wind_strength(wind_ms: float) -> float:
	## Shader wind strength for a wind speed, on the farm view's scale.
	return clampf(wind_ms / WIND_SCALE_MAX_MS, 0.0, 1.0)


static func row_z(row: int) -> float:
	## Rows run from z = 0 (front) towards -z (back).
	return -row * ROW_PITCH


static func cell_x(crop_key: String, col: int) -> float:
	## Cells are centred on x = 0 using the crop's own cell footprint.
	var cell: float = CROP_LAYOUT[crop_key]["cell"]
	return (float(col) - float(COLS.size() - 1) * 0.5) * cell


static func row_camera(row: int, viewport_size: Vector2) -> Dictionary:
	## Close-up camera pose for one crop row: far enough back that all six
	## cells fit the frame width, aimed at mid-plant height.
	var crop_key: String = CROPS[row]
	var height: float = CROP_HEIGHTS.get(crop_key, 2.0)
	var cell: float = CROP_LAYOUT[crop_key]["cell"]
	var cz: float = row_z(row)
	var aspect: float = viewport_size.x / maxf(viewport_size.y, 1.0)
	var half_fov: float = deg_to_rad(CAMERA_FOV) * 0.5
	var row_width: float = COLS.size() * cell + 0.6
	var distance: float = row_width / (2.0 * tan(half_fov) * aspect)
	var pos := Vector3(0.0, height * 0.55 + 0.4, cz + distance)
	var target := Vector3(0.0, height * 0.45, cz)
	return {"pos": pos, "target": target}


func _setup_lighting() -> void:
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, -20, 0)
	light.shadow_enabled = true
	add_child(light)
	var ambient := WorldEnvironment.new()
	var env := Environment.new()
	env.ambient_light_color = Color.WHITE
	env.ambient_light_energy = 0.5
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.85, 0.88, 0.90)
	ambient.environment = env
	add_child(ambient)


func _cell_visuals(crop_key: String, cfg: Dictionary) -> Dictionary:
	## Renderer inputs for one grid cell, through the same mapping the farm view uses.
	var tile := {
		"crop_key": crop_key,
		"crop_stage": cfg["stage"],
		"lai": cfg["lai"],
		"grain_g_m2": cfg["grain"],
		"dev_stage": cfg["dev"],
		"lai_peak": cfg["lai_peak"],
	}
	return CropVisuals.derive_visual_state(tile)


func _build_grid() -> void:
	var stresses := {"water": 0.0, "n": 0.0, "p": 0.0, "fe": 0.0, "zn": 0.0}
	for row in range(CROPS.size()):
		var crop_key: String = CROPS[row]
		var layout: Dictionary = CROP_LAYOUT[crop_key]
		var cell: float = layout["cell"]
		var count: int = layout["count"]
		var spacing: float = layout["spacing"]
		var height: float = CROP_HEIGHTS.get(crop_key, 2.0)
		var cz: float = row_z(row)
		var row_node := Node3D.new()
		row_node.name = crop_key
		add_child(row_node)
		_rows.append(row_node)
		var col_labels := Node3D.new()
		col_labels.name = "col_labels"
		row_node.add_child(col_labels)
		_col_labels.append(col_labels)
		# Text scales with the cell so the widest column label fits its cell.
		var text_size: float = LABEL_SIZE_PER_M * cell
		var label_x: float = cell_x(crop_key, 0) - cell * 0.5 - 0.4
		_add_label(row_node, crop_key, Vector3(label_x, height * 0.5, cz), text_size)
		for col in range(COLS.size()):
			var cfg: Dictionary = COLS[col]
			var vis: Dictionary = _cell_visuals(crop_key, cfg)
			var cx: float = cell_x(crop_key, col)
			_add_label(col_labels, cfg["label"], Vector3(cx, height + 0.2, cz), text_size)
			for pi in range(count):
				var seed_val: int = row * 100 + col * 10 + pi
				var plant := CropVisuals.create_3d_plant(
					crop_key,
					vis["growth"],
					vis["senescence"],
					stresses,
					vis["repro"],
					seed_val,
					vis["yield_frac"]
				)
				# Plants stand off the exact lattice and lean slightly, as
				# the farm view places them.
				var offset: float = (float(pi) - float(count - 1) * 0.5) * spacing
				offset += (CR.hash_val(seed_val, 90) - 0.5) * spacing * 0.5
				var dz: float = (CR.hash_val(seed_val, 91) - 0.5) * spacing * 0.6
				plant.transform = Transform3D(
					CropVisuals.natural_lean_basis(seed_val), Vector3(cx + offset, 0.0, cz + dz)
				)
				row_node.add_child(plant)
			_add_ground(row_node, Vector3(cx, -0.001, cz), cell, crop_key == "rice")


func _add_ground(parent: Node3D, pos: Vector3, cell: float, flooded: bool) -> void:
	var ground := MeshInstance3D.new()
	var gm := PlaneMesh.new()
	gm.size = Vector2(cell * 0.9, cell * 0.9)
	ground.mesh = gm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.30, 0.36, 0.34) if flooded else Color(0.35, 0.25, 0.15)
	ground.material_override = mat
	ground.position = pos
	parent.add_child(ground)


func _add_label(parent: Node3D, text: String, pos: Vector3, pixel_size: float) -> void:
	var label := Label3D.new()
	label.text = text
	label.font_size = 40
	label.outline_size = 10
	label.pixel_size = pixel_size
	label.modulate = Color(0.12, 0.12, 0.12)
	label.outline_modulate = Color(0.95, 0.95, 0.95)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	# Anchor the block at its bottom so extra lines grow upward, away from
	# the plants beneath.
	label.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	label.position = pos
	parent.add_child(label)


func _process(_delta: float) -> void:
	if _shot_idx >= _shots.size():
		return
	if _shot_idx < 0:
		_advance_shot()
		return
	_frames_since_move += 1
	if _frames_since_move >= SETTLE_FRAMES:
		_capture_screenshot(_shots[_shot_idx]["path"])
		_advance_shot()


func _advance_shot() -> void:
	_shot_idx += 1
	if _shot_idx >= _shots.size():
		return
	var shot: Dictionary = _shots[_shot_idx]
	# Close-ups show only their own row so nearer rows cannot occlude it;
	# the overview keeps column labels on the front row only.
	var active_row: int = shot["row"]
	for row in range(_rows.size()):
		_rows[row].visible = active_row < 0 or row == active_row
		_col_labels[row].visible = active_row >= 0 or row == 0
	_camera.look_at_from_position(shot["pos"], shot["target"])
	_frames_since_move = 0


func _capture_screenshot(path: String) -> void:
	var img: Image = get_viewport().get_texture().get_image()
	if img == null:
		push_warning("CropGridCapture: failed to get viewport image")
		return
	var err: int = img.save_png(path)
	if err == OK:
		print("Crop grid saved to: ", path)
	else:
		push_warning("CropGridCapture: save failed with error %d" % err)
