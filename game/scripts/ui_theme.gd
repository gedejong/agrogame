class_name UiTheme
extends RefCounted
## Shared UI theme constants and StyleBoxFlat factories.
## Dark earth-tone aesthetic: SimCity 4 / Frostpunk control panels.

# --- Background & border ---
const BG_COLOR := Color(0.08, 0.07, 0.06, 0.93)
const BG_COLOR_LIGHTER := Color(0.12, 0.11, 0.10, 0.93)
const BORDER_COLOR := Color(0.3, 0.27, 0.22, 0.5)
const SHADOW_COLOR := Color(0, 0, 0, 0.3)
const SHADOW_SIZE := 4
const CORNER_RADIUS := 8

# --- Text colors ---
const HEADER_COLOR := Color(0.82, 0.76, 0.65)
const BODY_COLOR := Color(0.78, 0.76, 0.72)
const MUTED_COLOR := Color(0.55, 0.52, 0.48)
const VALUE_COLOR := Color(0.78, 0.76, 0.72)

# --- Button colors ---
const BTN_NORMAL_BG := Color(0.12, 0.11, 0.10, 0.9)
const BTN_HOVER_BG := Color(0.16, 0.14, 0.12, 0.95)
const BTN_PRESSED_BG := Color(0.07, 0.06, 0.05, 0.95)
const BTN_DISABLED_BG := Color(0.10, 0.09, 0.08, 0.6)
const BTN_BORDER := Color(0.3, 0.27, 0.22, 0.5)
const BTN_HOVER_BORDER := Color(0.5, 0.44, 0.35, 0.7)
const BTN_CORNER_RADIUS := 6

# --- Icon tint ---
const ICON_TINT := Color(0.82, 0.76, 0.65)

# --- Separator ---
const SEPARATOR_COLOR := Color(0.3, 0.27, 0.22, 0.4)


static func create_bar_style(top_round: bool = false) -> StyleBoxFlat:
	"""Dark bar style (for top bar / action bar strips)."""
	var s := create_panel_style()
	if not top_round:
		s.corner_radius_top_left = 0
		s.corner_radius_top_right = 0
	return s


static func create_panel_style() -> StyleBoxFlat:
	"""Dark panel with rounded corners, border, and shadow."""
	var s := StyleBoxFlat.new()
	s.bg_color = BG_COLOR
	s.corner_radius_top_left = CORNER_RADIUS
	s.corner_radius_top_right = CORNER_RADIUS
	s.corner_radius_bottom_left = CORNER_RADIUS
	s.corner_radius_bottom_right = CORNER_RADIUS
	s.content_margin_left = 10
	s.content_margin_right = 10
	s.content_margin_top = 8
	s.content_margin_bottom = 8
	s.border_width_left = 1
	s.border_width_right = 1
	s.border_width_top = 1
	s.border_width_bottom = 1
	s.border_color = BORDER_COLOR
	s.shadow_color = SHADOW_COLOR
	s.shadow_size = SHADOW_SIZE
	return s


static func create_button_style(state: String) -> StyleBoxFlat:
	"""Button StyleBoxFlat for normal/hover/pressed/disabled."""
	var s := StyleBoxFlat.new()
	s.corner_radius_top_left = BTN_CORNER_RADIUS
	s.corner_radius_top_right = BTN_CORNER_RADIUS
	s.corner_radius_bottom_left = BTN_CORNER_RADIUS
	s.corner_radius_bottom_right = BTN_CORNER_RADIUS
	s.content_margin_left = 8
	s.content_margin_right = 8
	s.content_margin_top = 4
	s.content_margin_bottom = 4
	s.border_width_left = 1
	s.border_width_right = 1
	s.border_width_top = 1
	s.border_width_bottom = 1
	match state:
		"hover":
			s.bg_color = BTN_HOVER_BG
			s.border_color = BTN_HOVER_BORDER
		"pressed":
			s.bg_color = BTN_PRESSED_BG
			s.border_color = BTN_BORDER
		"disabled":
			s.bg_color = BTN_DISABLED_BG
			s.border_color = Color(0.2, 0.18, 0.15, 0.3)
		_:
			s.bg_color = BTN_NORMAL_BG
			s.border_color = BTN_BORDER
	return s


static func style_button(btn: Button) -> void:
	"""Apply full dark theme to a Button (all 4 states + text colors)."""
	btn.add_theme_stylebox_override("normal", create_button_style("normal"))
	btn.add_theme_stylebox_override("hover", create_button_style("hover"))
	btn.add_theme_stylebox_override("pressed", create_button_style("pressed"))
	btn.add_theme_stylebox_override("disabled", create_button_style("disabled"))
	btn.add_theme_color_override("font_color", BODY_COLOR)
	btn.add_theme_color_override("font_hover_color", HEADER_COLOR)
	btn.add_theme_color_override("font_pressed_color", MUTED_COLOR)
	btn.add_theme_color_override("font_disabled_color", Color(0.4, 0.37, 0.33, 0.5))
	btn.add_theme_color_override("icon_normal_color", ICON_TINT)
	btn.add_theme_color_override("icon_hover_color", HEADER_COLOR)


static func wrap_in_panel(node: Control, style: StyleBoxFlat) -> PanelContainer:
	"""Reparent a Control inside a styled PanelContainer at the same tree position."""
	var parent: Node = node.get_parent()
	var idx: int = node.get_index()
	var rect := Rect2(node.offset_left, node.offset_top, node.offset_right, node.offset_bottom)
	parent.remove_child(node)
	var bg := PanelContainer.new()
	bg.add_theme_stylebox_override("panel", style)
	bg.add_child(node)
	parent.add_child(bg)
	parent.move_child(bg, idx)
	bg.offset_left = rect.position.x
	bg.offset_top = rect.position.y
	bg.offset_right = rect.size.x
	bg.offset_bottom = rect.size.y
	return bg


static func style_vseparator(sep: VSeparator) -> void:
	"""Apply muted earth-tone style to a VSeparator."""
	var s := StyleBoxFlat.new()
	s.bg_color = SEPARATOR_COLOR
	s.content_margin_left = 4
	s.content_margin_right = 4
	sep.add_theme_stylebox_override("separator", s)


static func style_popup_menu(popup: PopupMenu) -> void:
	"""Apply dark theme to a PopupMenu."""
	var panel_style := create_panel_style()
	panel_style.content_margin_left = 4
	panel_style.content_margin_right = 4
	panel_style.content_margin_top = 4
	panel_style.content_margin_bottom = 4
	popup.add_theme_stylebox_override("panel", panel_style)
	var hover_style := StyleBoxFlat.new()
	hover_style.bg_color = BTN_HOVER_BG
	hover_style.corner_radius_top_left = 4
	hover_style.corner_radius_top_right = 4
	hover_style.corner_radius_bottom_left = 4
	hover_style.corner_radius_bottom_right = 4
	popup.add_theme_stylebox_override("hover", hover_style)
	popup.add_theme_color_override("font_color", BODY_COLOR)
	popup.add_theme_color_override("font_hover_color", HEADER_COLOR)


static func replace_spacers(parent: Node, names: Array) -> void:
	"""Replace named spacer Controls with styled VSeparators."""
	for spacer_name: String in names:
		var spacer: Control = parent.get_node(spacer_name)
		var sep := VSeparator.new()
		style_vseparator(sep)
		var idx: int = spacer.get_index()
		parent.remove_child(spacer)
		spacer.queue_free()
		parent.add_child(sep)
		parent.move_child(sep, idx)


static func style_label(label: Label, type: String) -> void:
	"""Set label font color by type: header, body, muted, value."""
	match type:
		"header":
			label.add_theme_color_override("font_color", HEADER_COLOR)
		"muted":
			label.add_theme_color_override("font_color", MUTED_COLOR)
		"value":
			label.add_theme_color_override("font_color", VALUE_COLOR)
		_:
			label.add_theme_color_override("font_color", BODY_COLOR)
