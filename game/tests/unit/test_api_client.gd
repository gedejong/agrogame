extends GutTest
## Unit tests for ApiClient — verifies construction and configuration.

const ApiClientScript = preload("res://scripts/api_client.gd")


func test_base_url_points_to_localhost() -> void:
	assert_eq(
		ApiClientScript.BASE_URL,
		"http://localhost:8000/api/v1",
		"API base URL should point to local FastAPI server",
	)


func test_instantiation_succeeds() -> void:
	var client = ApiClientScript.new()
	assert_not_null(client, "ApiClient should instantiate")
	client.free()


func test_has_create_game_method() -> void:
	var client = ApiClientScript.new()
	assert_true(client.has_method("create_game"), "ApiClient should expose create_game()")
	client.free()
