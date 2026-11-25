# ADR-022: Diorama presentation: the soil on the farm's cut edges, a world around the farm

## Status

Accepted (Edwin, 2026-11-25), with three changes to the proposal:
- assets are downloaded and realistic, not procedural low-poly (decision 5);
- the slab is drawn deeper than the simulated profile, for its look (decision 1);
- the shaded face gets a fill light (decision 1). Withdrawn on 2026-11-25 by
  the lighting amendment below.

**Amended (Edwin, 2026-11-25; #680):** no fill on the shaded face, more sky
ambient, and one cited soil colour for the tops and the faces (decision 1,
Lighting).

Edwin chose the direction on 2026-11-24 ("Yes to 1 and 2. Also, would be nice to
have a bit of elevation").

Amends [ADR-005](ADR-005-frontend-architecture.md) ("The Underground", and its
stylised art direction for world assets) and
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
     which the model caps at the profile bottom (#651), with density fading with
     depth.
   - **Depth (Edwin, 2026-11-25).**
     - The simulated profile is drawn at true vertical scale, so roots and
       horizons keep their real proportions against the canopy.
     - Below it, the slab continues for its look, to 4 to 8 times the profile's
       depth. It shows realistic regional layers (subsoil, parent material,
       weathered rock), artefacts such as stones, old roots and gravel lenses,
       and surface relief through normal or bump maps.
     - The extension is decorative: no simulation value drives it.
   - **Lighting (amended 2026-11-25, #680).** The faces and their decorative
     extension take the scene's light alone, from `farm_environment.tres`; the
     fill on the face turned from the sun is withdrawn. Edwin, on the slab with
     the fill: "I would expect the
     color of the 'top' of the soil (what you can normally see), to extend
     normally to the cutout, but now, due to the extra lighting, it seems
     unrealistic, especially on the left side (where it is in the shadow). I
     think we need a bit more overall ambient light, and it's ok to make the
     left side darker to fit the shadows."
     - The ambient rises instead, as a gain on the sky's radiance map
       (`farm_sky.gdshader`), so the background sky does not brighten. On a
       clear day the shaded face reads about 0.40 of the sunlit one in
       scene-linear light: the upper end of 0.26 to 0.42 for an isotropic sky
       (Liu & Jordan 1963) at a clear-day diffuse fraction of 0.165 to 0.24
       (Erbs, Klein & Duffie 1982). The gain rises by a quarter at full
       overcast. The tone mapper stays Filmic, with its exposure re-balanced so
       the canopy's lightness holds (#637).
     - The top and the face's top band take one colour: the Munsell value of
       the cited mapping, and a cited Munsell hue and chroma per soil preset
       and layer. Soils differ as much as the cited ones do, and no more.
   - Under decorative land, the face shows a static profile typical of the
     scenario's region.
   - **Soil detail follows the same rule: drawn from the simulation where the
     model holds the quantity, decorative only outside it.**
     - Old root channels come from the biopore density per layer, the channels
       decayed roots leave (ADR-009).
     - Grey and rust redox mottles appear where a layer's redox potential drops
       into the iron-reducing range (Vepraskas 1992). They are the visible trace
       of a fluctuating water table.
     - Below the simulated profile, the decorative extension shows regional
       parent material: rock fragments, ironstone gravel or marine clay.
     - No aquifer or water table is drawn while the water balance drains freely
       and has no groundwater. Adding one is a hydrology decision, not a
       presentation one.
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
5. **Assets are downloaded and realistic (Edwin, 2026-11-25: "not low-poly, you
   can download assets").** Buildings, trees, props, terrain and soil materials
   come from asset libraries as glTF models and PBR texture sets (albedo,
   normal, roughness), not from procedural low-poly meshes. This amends
   ADR-005's stylised art direction for world assets.
   - **Licence.** Use CC0 sources first, such as Poly Haven and ambientCG.
     Anything that needs attribution, or carries any other licence, needs
     Edwin's approval first.
   - **Provenance.** `game/assets/CREDITS.md` records, for every file: its
     source URL, author, licence and download date, plus any edits made.
   - **Review.** Binary assets can't be reviewed as text. Each asset PR
     therefore carries `/visual-check` frames for every scenario it touches,
     and a GUT test that checks the asset loads and has its credits entry.
   - **Weight.** Import at the smallest resolution that reads at default zoom.
     Each PR reports the bytes it adds. **Git LFS (Edwin, 2026-11-25; #652):**
     downloaded binaries under `game/assets/materials/` and
     `game/assets/models/` live in Git LFS; the textures already in Git stay
     there. CI jobs that load assets check out with `lfs: true`. Each asset PR
     reports its LFS bytes and the projected monthly CI download against the
     free 10 GiB; the PR that takes LFS past about 20 MB at HEAD proposes a CI
     cache.
   - Placement, variety and seeding stay procedural: the scenario's climate key
     and a deterministic seed choose and place assets.
6. **Performance budget.** At default zoom, the slab and surroundings together
   add at most 3 ms of GPU frame time over the baseline after #640, measured on
   the development machine. Realistic assets keep to it through levels of
   detail, instancing and texture sizes; a PR that cannot meet it reports why,
   and Edwin decides. Decorative crops use instanced meshes, not the
   managed-field crop renderer.
7. **Framing.** The default camera keeps the managed fields as the subject;
   zooming out reveals the surroundings.

## Consequences

- About 2,350 lines of client code and their tests are removed. #634 closes as
  superseded, and so does the cutaway and flow-tube half of #641.
- The soil is visible all the time, so weather and growth show up underground
  without the player opening anything.
- Fewer layers are visible at once than in the pit, and decorative land gives
  no data. The Soil Analysis panel remains the place for detail.
- New code and assets for the slab, terrain, vegetation and buildings need
  visual review for each scenario; `/visual-check` frames per climate become
  part of each PR.
- Downloaded assets add binary weight and a licence duty; `CREDITS.md` and the
  load-and-credits test carry that duty.
- Farm-business features (storage, land, machinery) get a physical home in the
  farmyard.

## Alternatives Considered

- **Keep the pit but declutter it.** This keeps the mode Edwin finds unnatural
  and the hidden-tile machinery.
- **A 2D profile chart in a side panel.** Clear, but it removes the soil from
  the world, and ADR-005's goal is that the player sees the soil as part of the
  land.
- **Procedural low-poly assets generated in GDScript.** Reviewable as text and
  reproducible, but Edwin rejected the low-poly look on 2026-11-25.
- **The slab at the simulated depth only (1×) or exaggerated (2×).** At 1×
  the face is about 31 px tall at 1280×720 and reads poorly; 2× doubles the
  roots against the canopy. Edwin chose true scale plus a decorative extension
  below.
- **Slope on managed fields now.** It needs hydrology changes (above); this ADR
  keeps elevation visual.

## References

- [ADR-005](ADR-005-frontend-architecture.md),
  [ADR-007](ADR-007-3d-rendering-migration.md)
- Epic #645 (children #646 to #649); #634 (roots drawn at about twice their
  depth), #641 (stress tints, cutaway
  colours), #637 / PR #640 (farm environment and lighting)
- Vepraskas, M. J. (1992). *Redoximorphic Features for Identifying Aquic
  Conditions*. Technical Bulletin 301, North Carolina Agricultural Research
  Service.
- Williams, J. R. (1995). The EPIC model. In V. P. Singh (Ed.), *Computer
  Models of Watershed Hydrology*, pp. 909–1000. Water Resources Publications.
