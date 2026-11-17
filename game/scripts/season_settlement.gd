class_name SeasonSettlement
extends RefCounted
## End-of-season settlement state for the farm view (#518).
##
## The /step that completes a season settles every standing crop on the server,
## which then refuses a Harvest until the next season starts. This helper tracks
## that from /step responses, gates the Harvest button accordingly, and formats
## the end-of-season status line from GET /report.

const SETTLED_TOOLTIP := "Season settled: start the next season"

## True from a /step response with season_complete until one without it.
var settled: bool = false


func observe_step(data: Dictionary) -> bool:
	"""Record a successful /step response; true when it reports a completed season."""
	settled = bool(data.get("season_complete", false))
	return settled


func apply_harvest_button(button: Button, has_crop: bool, has_selection: bool) -> void:
	"""Enable Harvest only for a selected standing crop in an unsettled season."""
	button.disabled = settled or not has_crop
	if settled:
		button.tooltip_text = SETTLED_TOOLTIP
	elif has_crop:
		button.tooltip_text = "Harvest the standing crop on this patch"
	elif has_selection:
		button.tooltip_text = "No standing crop to harvest on this patch"
	else:
		button.tooltip_text = "Select a patch with a standing crop to harvest"


static func report_text(success: bool, report: Dictionary) -> String:
	"""Status line for a completed season; the plain fallback if /report failed."""
	if not success:
		return "Season complete"
	return (
		"Season complete: revenue %d, profit %d credits"
		% [int(report.get("revenue_credits", 0)), int(report.get("profit_credits", 0))]
	)
