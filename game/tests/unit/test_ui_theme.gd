extends GutTest
## Tests for shared UI theme constants and factory methods.

const ThemeRef = preload("res://scripts/ui_theme.gd")


func test_panel_constants_exist() -> void:
	assert_ne(ThemeRef.PANEL_BG, Color(), "PANEL_BG should be defined")
	assert_ne(ThemeRef.BORDER_COLOR, Color(), "BORDER_COLOR should be defined")
	assert_ne(ThemeRef.TEXT_PRIMARY, Color(), "TEXT_PRIMARY should be defined")
	assert_ne(ThemeRef.TEXT_SECONDARY, Color(), "TEXT_SECONDARY should be defined")
	assert_ne(ThemeRef.ICON_TINT, Color(), "ICON_TINT should be defined")
	assert_gt(ThemeRef.CORNER_RADIUS, 0, "CORNER_RADIUS should be positive")
	assert_gt(ThemeRef.SHADOW_SIZE, 0, "SHADOW_SIZE should be positive")


func test_accent_colors_exist() -> void:
	assert_ne(ThemeRef.ACCENT_GREEN, Color(), "ACCENT_GREEN should be defined")
	assert_ne(ThemeRef.ACCENT_RED, Color(), "ACCENT_RED should be defined")
	assert_ne(ThemeRef.ACCENT_GOLD, Color(), "ACCENT_GOLD should be defined")
	assert_ne(ThemeRef.ACCENT_BLUE, Color(), "ACCENT_BLUE should be defined")


func test_create_panel_style_returns_stylebox() -> void:
	var style: StyleBoxFlat = ThemeRef.create_panel_style()
	assert_not_null(style, "create_panel_style should return a StyleBoxFlat")
	assert_eq(style.bg_color, ThemeRef.PANEL_BG, "Panel bg should match PANEL_BG")
	assert_eq(
		style.corner_radius_top_left,
		ThemeRef.CORNER_RADIUS,
		"Corner radius should match",
	)
	assert_eq(style.shadow_size, ThemeRef.SHADOW_SIZE, "Shadow size should match")
	assert_eq(style.border_width_left, 1, "Border should be 1px")


func test_create_bar_style() -> void:
	var style: StyleBoxFlat = ThemeRef.create_bar_style()
	assert_eq(style.bg_color, ThemeRef.BAR_BG, "Bar bg should be darker")
	assert_eq(style.corner_radius_top_left, 0, "Top corners should be flat")
	assert_eq(
		style.corner_radius_bottom_left,
		ThemeRef.CORNER_RADIUS,
		"Bottom corners should be rounded",
	)


func test_create_inner_card_style() -> void:
	var style: StyleBoxFlat = ThemeRef.create_inner_card_style()
	assert_eq(style.bg_color, ThemeRef.INNER_CARD_BG, "Inner card bg should match")
	assert_eq(
		style.corner_radius_top_left,
		ThemeRef.INNER_RADIUS,
		"Inner radius should match",
	)


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
		ThemeRef.TEXT_PRIMARY,
		"Header label should be white",
	)


func test_style_label_muted() -> void:
	var lbl := Label.new()
	add_child_autofree(lbl)
	ThemeRef.style_label(lbl, "muted")
	assert_eq(
		lbl.get_theme_color("font_color"),
		ThemeRef.TEXT_SECONDARY,
		"Muted label should be secondary grey",
	)
