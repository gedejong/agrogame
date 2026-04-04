extends GutTest

const SoilView3DScript = preload("res://scripts/soil_view_3d.gd")


func test_layer_colors_defined() -> void:
	assert_true(SoilView3DScript.LAYER_COLORS.has("sand"))
	assert_true(SoilView3DScript.LAYER_COLORS.has("loam"))
	assert_true(SoilView3DScript.LAYER_COLORS.has("clay"))


func test_profile_layers_sandy() -> void:
	var layers: Array = SoilView3DScript.get_profile_layers("sandy")
	assert_eq(layers.size(), 3, "Sandy has 3 layers")
	assert_eq(layers[0]["texture"], "sand")


func test_profile_layers_clay() -> void:
	var layers: Array = SoilView3DScript.get_profile_layers("clay")
	assert_eq(layers.size(), 3, "Clay has 3 layers")
	assert_eq(layers[0]["texture"], "clay")


func test_profile_layers_organic() -> void:
	var layers: Array = SoilView3DScript.get_profile_layers("organic")
	assert_eq(layers.size(), 3, "Organic/loam has 3 layers")
	assert_eq(layers[0]["texture"], "loam")


func test_create_open_box_mesh() -> void:
	var mesh: ArrayMesh = SoilView3DScript._create_open_box(1.0, 0.5, 1.0)
	assert_not_null(mesh, "Open box mesh created")
	# 5 faces x 2 triangles x 3 vertices = 30 vertices
	assert_eq(mesh.get_faces().size(), 30, "5 quad faces = 30 vertices")
