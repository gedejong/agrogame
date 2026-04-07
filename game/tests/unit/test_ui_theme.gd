extends GutTest
## Tests for shared UI theme constants and factory methods.

const ThemeRef = preload("res://scripts/ui_theme.gd")


func test_panel_and_accent_constants() -> void:
	assert_ne(ThemeRef.PANEL_BG, Color(), "PANEL_BG should be defined")
	assert_ne(ThemeRef.BORDER_COLOR, Color(), "BORDER_COLOR should be defined")
	assert_ne(ThemeRef.TEXT_PRIMARY, Color(), "TEXT_PRIMARY should be defined")
	assert_ne(ThemeRef.TEXT_SECONDARY, Color(), "TEXT_SECONDARY should be defined")
	assert_gt(ThemeRef.CORNER_RADIUS, 0, "CORNER_RADIUS should be positive")
	assert_gt(ThemeRef.SHADOW_SIZE, 0, "SHADOW_SIZE should be positive")
	assert_ne(ThemeRef.ACCENT_GREEN, Color())
	assert_ne(ThemeRef.ACCENT_RED, Color())
	assert_ne(ThemeRef.ACCENT_GOLD, Color())
	assert_ne(ThemeRef.ACCENT_BLUE, Color())
	assert_ne(ThemeRef.ACCENT_LIME, Color())


func test_create_panel_style_opaque_and_transparent() -> void:
	var opaque: StyleBoxFlat = ThemeRef.create_panel_style()
	assert_eq(opaque.bg_color, ThemeRef.PANEL_BG)
	assert_eq(opaque.corner_radius_top_left, ThemeRef.CORNER_RADIUS)
	assert_eq(opaque.shadow_size, ThemeRef.SHADOW_SIZE)
	assert_eq(opaque.border_width_left, 1)
	var clear: StyleBoxFlat = ThemeRef.create_panel_style(true)
	assert_eq(clear.bg_color, Color(0, 0, 0, 0), "Transparent bg should be clear")
	assert_eq(clear.corner_radius_top_left, ThemeRef.CORNER_RADIUS)
	assert_eq(clear.border_width_left, 1)


func test_create_bar_and_hud_styles() -> void:
	var bar: StyleBoxFlat = ThemeRef.create_bar_style()
	assert_eq(bar.bg_color, ThemeRef.BAR_BG)
	assert_eq(bar.corner_radius_top_left, 0)
	assert_eq(bar.corner_radius_bottom_left, ThemeRef.CORNER_RADIUS)
	var bar_t: StyleBoxFlat = ThemeRef.create_bar_style(true)
	assert_eq(bar_t.bg_color, Color(0, 0, 0, 0))
	var hud: StyleBoxFlat = ThemeRef.create_hud_style()
	assert_eq(hud.corner_radius_bottom_left, 0)
	assert_eq(hud.content_margin_left, 12)


func test_create_inner_card_style() -> void:
	var style: StyleBoxFlat = ThemeRef.create_inner_card_style()
	assert_eq(style.bg_color, ThemeRef.INNER_CARD_BG)
	assert_eq(style.corner_radius_top_left, ThemeRef.INNER_RADIUS)


func test_button_styles_all_states() -> void:
	var normal: StyleBoxFlat = ThemeRef.create_button_style("normal")
	var hover: StyleBoxFlat = ThemeRef.create_button_style("hover")
	var pressed: StyleBoxFlat = ThemeRef.create_button_style("pressed")
	var disabled: StyleBoxFlat = ThemeRef.create_button_style("disabled")
	assert_eq(normal.bg_color, ThemeRef.BTN_NORMAL_BG)
	assert_eq(hover.bg_color, ThemeRef.BTN_HOVER_BG)
	assert_eq(hover.border_color, ThemeRef.BTN_HOVER_BORDER)
	assert_eq(pressed.bg_color, ThemeRef.BTN_PRESSED_BG)
	assert_eq(disabled.bg_color, ThemeRef.BTN_DISABLED_BG)
	assert_ne(normal.bg_color, hover.bg_color)
	assert_ne(normal.bg_color, pressed.bg_color)


func test_style_button_applies_overrides() -> void:
	var btn := Button.new()
	add_child_autofree(btn)
	ThemeRef.style_button(btn)
	assert_not_null(btn.get_theme_stylebox("normal") as StyleBoxFlat)


func test_style_label_types() -> void:
	var h := Label.new()
	add_child_autofree(h)
	ThemeRef.style_label(h, "header")
	assert_eq(h.get_theme_color("font_color"), ThemeRef.TEXT_PRIMARY)
	assert_true(h.uppercase, "Header should be uppercase")
	var b := Label.new()
	add_child_autofree(b)
	ThemeRef.style_label(b, "body")
	assert_eq(b.get_theme_color("font_color"), ThemeRef.TEXT_SECONDARY)
	var m := Label.new()
	add_child_autofree(m)
	ThemeRef.style_label(m, "muted")
	assert_eq(m.get_theme_color("font_color"), ThemeRef.TEXT_MUTED)


func test_style_vseparator() -> void:
	var sep := VSeparator.new()
	add_child_autofree(sep)
	ThemeRef.style_vseparator(sep)
	assert_true(sep.has_theme_stylebox_override("separator"))


func test_style_popup_menu() -> void:
	var popup := PopupMenu.new()
	add_child_autofree(popup)
	ThemeRef.style_popup_menu(popup)
	assert_true(popup.has_theme_stylebox_override("panel"))
	assert_true(popup.has_theme_stylebox_override("hover"))


func test_add_divider() -> void:
	var vbox := VBoxContainer.new()
	add_child_autofree(vbox)
	vbox.add_child(Label.new())
	vbox.add_child(Label.new())
	ThemeRef.add_divider(vbox, 1)
	assert_eq(vbox.get_child_count(), 3)
	assert_true(vbox.get_child(1) is HSeparator)


func test_wrap_in_panel() -> void:
	var parent := Control.new()
	add_child_autofree(parent)
	var child := HBoxContainer.new()
	parent.add_child(child)
	var bg: PanelContainer = ThemeRef.wrap_in_panel(child, ThemeRef.create_bar_style())
	assert_not_null(bg, "Should return PanelContainer")
	assert_eq(bg.get_parent(), parent)
	assert_eq(child.get_parent(), bg)
