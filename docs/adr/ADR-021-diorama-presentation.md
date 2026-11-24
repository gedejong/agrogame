# ADR-021: Diorama presentation: the soil on the farm's cut edges, a world around the farm

## Status

Proposed. Edwin chose the direction on 2026-11-24 ("Yes to 1 and 2. Also, would
be nice to have a bit of elevation"); this text awaits his acceptance.
Amends [ADR-005](ADR-005-frontend-architecture.md) ("The Underground") and
[ADR-007](ADR-007-3d-rendering-migration.md) (item 4, soil cutaway).

## Context

ADR-005 made the underground the game's differentiator and specified it as a
mode: click a patch and the camera slides into a 3D cross-section. In the code
on main, View Soil digs a pit into the field. It hides the three tiles in front
of the selection, raises a soil pillar with a highlighted outline and glass flow
tubes, and opens a Soil Analysis panel with fifteen readouts for each of three
layers. Five files carry the mode: `soil_view.gd` (504 lines),
`soil_cutaway_controller.gd` (265), `flow_tube.gd` (630), `flow_overlay.gd`
(822) and `soil_cutaway.gdshader` (127), with their tests.

Edwin's verdict after playing it (2026-11-24): he wanted only a bit of the soil
underneath, as an impression, and the pit is too much and feels unnatural. He
also wants the managed fields set in a landscape (neighbouring fields, trees, a
barn), some elevation, and eventually the whole business of running a farm.

The pit also carries a known defect: it draws roots at about twice the reported
depth (#634). A cosmetic fix there would polish a mode this ADR removes.

## Decision

1. **The world is a diorama slab.** The land is a finite slab, and its two
   camera-facing cut faces always show the soil beneath the surface above them.
   The managed fields sit at the front corner, so each front patch's own
   profile shows directly under it.
   - Under a managed patch, the face is drawn from the simulation and updated
     each day tick. Horizon boundaries come from `SoilProfile.layers`. Each
     horizon darkens with its organic carbon and with its water content
     relative to field capacity. Root traces reach `RootState.current_depth_cm`,
     with density fading with depth.
   - Under decorative land, the face shows a static profile typical of the
     scenario's region.
   - ADR-005's goal 2 (showing what happens underground) stands. It is now
     delivered as an ambient, always-visible edge, not as a mode.
2. **The pit cutaway is retired.** The pit, the hidden tiles, the pillar, the
   flow tubes and the cutaway shader go, with their tests; the tests cover only
   the retired code. View Soil opens the Soil Analysis panel, trimmed to a few
   headline values per layer, with the rest behind Expand.
3. **Surroundings.** A ring of non-simulated land frames the managed fields:
   - neighbouring fields in a regional rotation;
   - hedgerows or tree rows, a ditch and a farm track;
   - a farmyard with barn, farmhouse, silo and machine shed.

   The sets follow the scenario's climate key: a Dutch polder, Kenyan highland
   smallholdings, the Sahel. Surroundings show no simulation values and cannot
   be selected. Later farm-business epics may make them interactive (barn
   storage, renting a neighbouring field); each needs its own design.
4. **Elevation.** The surroundings get gentle, region-appropriate relief: a dike
   and a faint rise in the polder, hills in the Kenyan highlands, low dunes in
   the Sahel. The cut faces follow the terrain's top edge.
   - Managed fields stay level, because the water balance assumes level ground
     (the SCS curve number has no slope term).
   - Sloping a managed field would first need a slope-adjusted curve number
     (Williams 1995, as used in EPIC and SWAT) and erosion. That is a separate
     decision.
5. **Assets are procedural.** Terrain, plants, buildings and props are low-poly
   meshes generated in GDScript from deterministic per-scenario seeds. They are
   drawn in the established palette and lit by `farm_environment.tres`. No
   imported binary models: every asset stays reviewable as text and verifiable
   with a headless render.
6. **Performance budget.** At default zoom, the slab and surroundings together
   add at most 3 ms of GPU frame time over the baseline after #640, measured on
   the development machine. Decorative crops use instanced simple meshes, not
   the managed-field crop renderer.
7. **Framing.** The default camera keeps the managed fields as the subject;
   zooming out reveals the surroundings.

## Consequences

- About 2,350 lines of client code and their tests are removed. #634 closes as
  superseded, and so does the cutaway and flow-tube half of #641.
- The soil is visible all the time, so weather and growth show up underground
  without the player opening anything.
- Fewer layers are visible at once than in the pit, and decorative land gives
  no data. The Soil Analysis panel remains the place for detail.
- New code for the slab, terrain, vegetation and buildings needs visual review
  for each scenario; `/visual-check` frames per climate become part of each PR.
- Farm-business features (storage, land, machinery) get a physical home in the
  farmyard.

## Alternatives Considered

- **Keep the pit but declutter it.** This keeps the mode Edwin finds unnatural
  and the hidden-tile machinery.
- **A 2D profile chart in a side panel.** Clear, but it removes the soil from
  the world, and ADR-005's goal is that the player sees the soil as part of the
  land.
- **Imported glTF models.** These look richer, but they are binary assets that
  agents can neither review as text nor generate reproducibly. They could
  return for hero assets later.
- **Slope on managed fields now.** It needs hydrology changes (above); this ADR
  keeps elevation visual.

## References

- [ADR-005](ADR-005-frontend-architecture.md),
  [ADR-007](ADR-007-3d-rendering-migration.md)
- Epic #645 (children #646 to #649); #634 (roots drawn at about twice their
  depth), #641 (stress tints, cutaway
  colours), #637 / PR #640 (farm environment and lighting)
- Williams, J. R. (1995). The EPIC model. In V. P. Singh (Ed.), *Computer
  Models of Watershed Hydrology*, pp. 909–1000. Water Resources Publications.
