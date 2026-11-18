extends GutTest
## ApiClient's field-scoped calls (#548): every action, preview and forecast
## names its field, and create_game sends a scenario's fields as given. Split
## from test_api_client.gd to stay within gdlint max-public-methods; drives the
## same stubbed transports (StubClient, PreviewStubClient), with no network.

const ApiClientScript = preload("res://scripts/api_client.gd")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")


func _stub_client() -> ApiClientTest.StubClient:
	var api: ApiClientTest.StubClient = ApiClientTest.StubClient.new()
	add_child_autofree(api)
	return api


func _ignore(_ok: bool, _data: Dictionary) -> void:
	pass


func test_field_scoped_calls_take_a_field_id_without_default() -> void:
	# AC1: no call can fall back on a field its caller did not name.
	var client = ApiClientScript.new()
	var scoped := ["execute_action", "preview_action", "get_forecast"]
	for method: Dictionary in client.get_method_list():
		if method["name"] in scoped:
			assert_eq(method["args"][1]["name"], "field_id", "%s names the field" % method["name"])
			assert_eq(method["default_args"], [], "%s has no defaults" % method["name"])
			scoped.erase(method["name"])
	assert_eq(scoped, [], "all three found")
	var source := FileAccess.get_file_as_string("res://scripts/api_client.gd")
	assert_false(source.contains('"field_1"'), "no field_1 literal in api_client.gd")
	client.free()


func test_create_game_sends_the_fields_it_is_given() -> void:
	# AC1: the scenario's fields go out as given, two of them here.
	var api := _stub_client()
	var two := [
		{"field_id": "north", "patches": [{"crop_key": "maize"}]},
		{"field_id": "south", "patches": [{"crop_key": "rice"}]},
	]
	api.create_game(_ignore, two)
	var create: Dictionary = JSON.parse_string(api.sends[0][3])
	assert_eq(create.keys(), ["fields", "starting_credits"])
	assert_eq(create["fields"], two, "both fields, as given")
	assert_eq(int(create["starting_credits"]), 10000)


func test_field_scoped_calls_carry_the_field_they_are_given() -> void:
	# AC2: a preview's body (through PreviewStubClient, the #523 preview seam),
	# an action's body and the forecast URL (through StubClient) each name the
	# field they were called with. The forecast's id is URI-encoded.
	var previews: ApiClientTest.PreviewStubClient = ApiClientTest.PreviewStubClient.new()
	add_child_autofree(previews)
	var api := _stub_client()
	var ids := ["field_1", "back field&2"]
	for field_id: String in ids:
		previews.preview_action("g", field_id, "tillage", {}, _ignore)
		previews.resolve({})
		api.execute_action("g", field_id, "irrigate", {}, _ignore)
		api.reply_ok("action", {})
		api.get_forecast("g", field_id, _ignore)
		api.reply_ok("forecast", {})
	assert_eq(previews.field_ids, ids, "each preview's body")
	var actions: Array = api.sends.filter(func(s: Array) -> bool: return s[0] == "action")
	var named: Array = actions.map(
		func(s: Array) -> String: return JSON.parse_string(s[3])["field_id"]
	)
	assert_eq(named, ids, "each action's body")
	var forecast := ApiClientScript.BASE_URL + "/games/g/forecast?field_id="
	var urls: Array = api.sends.filter(func(s: Array) -> bool: return s[0] == "forecast")
	var want := [forecast + "field_1", forecast + "back%20field%262"]
	assert_eq(urls.map(func(s: Array) -> String: return s[1]), want, "each forecast's URL")
