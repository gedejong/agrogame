extends GutTest
## Tests for shared UI theme constants and factory methods.

const ThemeRef = preload("res://scripts/ui_theme.gd")


func test_constants_exist() -> void:
	assert_ne(ThemeRef.BG_COLOR, Color(), "BG_COLOR should be defined")
	assert_ne(ThemeRef.BORDER_COLOR, Color(), "BORDER_COLOR should be defined")
	assert_ne(ThemeRef.HEADER_COLOR, Color(), "HEADER_COLOR should be defined")
	assert_ne(ThemeRef.BODY_COLOR, Color(), "BODY_COLOR should be defined")
	assert_ne(ThemeRef.MUTED_COLOR, Color(), "MUTED_COLOR should be defined")
	assert_ne(ThemeRef.ICON_TINT, Color(), "ICON_TINT should be defined")
	assert_gt(ThemeRef.CORNER_RADIUS, 0, "CORNER_RADIUS should be positive")
	assert_gt(ThemeRef.SHADOW_SIZE, 0, "SHADOW_SIZE should be positive")


func test_create_panel_style_returns_stylebox() -> void:
	var style: StyleBoxFlat = ThemeRef.create_panel_style()
	assert_not_null(style, "create_panel_style should return a StyleBoxFlat")
	assert_eq(style.bg_color, ThemeRef.BG_COLOR, "Panel bg should match BG_COLOR")
	assert_eq(
		style.corner_radius_top_left,
		ThemeRef.CORNER_RADIUS,
		"Corner radius should match",
	)
	assert_eq(style.shadow_size, ThemeRef.SHADOW_SIZE, "Shadow size should match")
	assert_eq(style.border_width_left, 1, "Border should be 1px")


func test_create_button_style_normal() -> void:
	var style: StyleBoxFlat = ThemeRef.create_button_style("normal")
	assert_not_null(style, "Should return StyleBoxFlat for normal state")
	assert_eq(style.bg_color, ThemeRef.BTN_NORMAL_BG, "Normal bg should match")


func test_create_button_style_hover() -> void:
	var style: StyleBoxFlat = ThemeRef.create_button_style("hover")
	assert_eq(style.bg_color, ThemeRef.BTN_HOVER_BG, "Hover bg should match")
	assert_eq(
		style.border_color,
		ThemeRef.BTN_HOVER_BORDER,
		"Hover border should be brighter",
	)


func test_create_button_style_pressed() -> void:
	var style: StyleBoxFlat = ThemeRef.create_button_style("pressed")
	assert_eq(style.bg_color, ThemeRef.BTN_PRESSED_BG, "Pressed bg should be darker")


func test_create_button_style_disabled() -> void:
	var style: StyleBoxFlat = ThemeRef.create_button_style("disabled")
	assert_eq(style.bg_color, ThemeRef.BTN_DISABLED_BG, "Disabled bg should be dimmed")


func test_button_states_differ() -> void:
	var normal: StyleBoxFlat = ThemeRef.create_button_style("normal")
	var hover: StyleBoxFlat = ThemeRef.create_button_style("hover")
	var pressed: StyleBoxFlat = ThemeRef.create_button_style("pressed")
	assert_ne(normal.bg_color, hover.bg_color, "Normal and hover should differ")
	assert_ne(normal.bg_color, pressed.bg_color, "Normal and pressed should differ")


func test_style_button_applies_overrides() -> void:
	var btn := Button.new()
	add_child_autofree(btn)
	ThemeRef.style_button(btn)
	var normal_style: StyleBoxFlat = btn.get_theme_stylebox("normal") as StyleBoxFlat
	assert_not_null(normal_style, "Button should have normal stylebox override")


func test_style_label_header() -> void:
	var lbl := Label.new()
	add_child_autofree(lbl)
	ThemeRef.style_label(lbl, "header")
	assert_eq(
		lbl.get_theme_color("font_color"),
		ThemeRef.HEADER_COLOR,
		"Header label color should match",
	)


func test_style_label_body() -> void:
	var lbl := Label.new()
	add_child_autofree(lbl)
	ThemeRef.style_label(lbl, "body")
	assert_eq(
		lbl.get_theme_color("font_color"),
		ThemeRef.BODY_COLOR,
		"Body label color should match",
	)
