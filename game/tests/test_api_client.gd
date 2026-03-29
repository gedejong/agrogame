extends Node
## Unit test for ApiClient — verifies construction and configuration.
## Run with: godot --headless --script res://tests/test_api_client.gd

const ApiClientScript = preload("res://scripts/api_client.gd")


func _ready() -> void:
	print("--- ApiClient unit tests ---")
	test_base_url()
	test_instantiation()
	print("--- All tests passed ---")
	get_tree().quit()


func test_base_url() -> void:
	assert(ApiClientScript.BASE_URL == "http://localhost:8000/api/v1")
	print("PASS: base_url correct")


func test_instantiation() -> void:
	var client = ApiClientScript.new()
	assert(client != null)
	client.free()
	print("PASS: instantiation")
