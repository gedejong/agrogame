# AgroGame Art Guide

Visual direction and specifications for all game art assets.

## Visual Direction

**Theme**: "Monument Valley meets agricultural textbook" (ADR-005)

Clean, minimalist isometric style with:
- Flat/low-poly surfaces with subtle texture detail
- Muted earth tones for soil and environment
- Vivid but natural greens for healthy crops, warm yellows/reds for stress
- Soft shadows and clean outlines
- Educational readability — a player should be able to identify soil type and crop stage at a glance

**Reference games**: Monument Valley, Alto's Adventure, Pocket City, Stardew Valley (for crop stage clarity, not pixel style)

## Color Space Rules (HSV Guardrails)

All assets must stay within these HSV bounds to ensure visual consistency across agents and sprites. The goal is a clear visual hierarchy: **soils are muted, crops are vivid, UI accents are bold**.

### Soil & Environment (earth tones)
| Property | Range | Rationale |
|----------|-------|-----------|
| Hue | 30–36° | Warm browns. Never blue-shifted, never orange. |
| Saturation | 15–55% | Soils are always muted — never vivid. |
| Value | 29–87% | Full range: degraded soil is light (V ~87%), rich soil is dark (V ~29%). Most tiles sit 55–83%. |

### Crops (greens → gold)
| Property | Range | Rationale |
|----------|-------|-----------|
| Hue | 69–98° (growing), 43–50° (mature/gold) | Green shifts to warm gold at harvest. |
| Saturation | 50–80% | Crops are the most vivid elements on screen. Always more saturated than soil. |
| Value | 48–85% | Seedlings are brighter/lighter, mature canopy is darker. |

### Stress States
| Property | Range | Rationale |
|----------|-------|-----------|
| Hue | Same range as crops | Stress is shown by desaturation and value shift, not hue change. |
| Saturation | 10–20% lower than healthy equivalent | Visibly washed out compared to healthy crop. |
| Value | Shift toward yellow-brown (H ~43°) | Conveys drying/dying. |

### UI Accents (grades, P&L, alerts)
| Property | Range | Rationale |
|----------|-------|-----------|
| Hue | Unrestricted (green, red, yellow, blue as needed) | Semantic color use. |
| Saturation | 70–80% | These must pop against muted backgrounds. |
| Value | 80–90% | Bright and clear. |

### Visual Hierarchy Summary
```
UI accents   S > 70%   ← boldest, draws attention for feedback
Crops        S 50–80%  ← vivid, the main visual focus during gameplay
Soil         S < 55%   ← muted backdrop, never competes with crops
```

When in doubt: if a soil tile looks more vivid than a crop sprite, the soil is too saturated. If a crop sprite blends into the soil, the crop needs more saturation.

## Color Palette

### Soil Tones
| Soil Type | Base Color | Hex | Notes |
|-----------|-----------|-----|-------|
| Sandy | Warm tan | `#d4b896` | Dry, light, warm undertone |
| Sandy (wet) | Dark tan | `#a8906e` | Visibly darker when moist |
| Loam/Organic | Rich brown | `#8b6f47` | Medium, neutral warmth |
| Loam (wet) | Dark brown | `#5c4a30` | Clear moisture darkening |
| Clay | Cool grey-brown | `#9a8b7a` | Cooler undertone than sandy |
| Clay (wet) | Dark cool grey | `#6b5f52` | Blue-grey shift when wet |
| Degraded (<1% SOM) | Pale beige | `#ddd0be` | Visibly washed out |
| Rich (>5% SOM) | Deep earth | `#4a3520` | Dark, healthy-looking |

### Crop Greens (by growth stage)
| Stage | Color | Hex | Notes |
|-------|-------|-----|-------|
| Seedling | Pale lime | `#a8d86a` | Young, light green |
| Vegetative | Medium green | `#5b9e2a` | Strong growth |
| Flowering | Deep green + accent | `#3d7a1a` | Mature canopy, flower color varies by crop |
| Grain fill | Yellow-green | `#8fb83a` | Transitioning to harvest |
| Mature/Harvest | Gold/brown | `#c8a832` | Ready for harvest |

### Stress Indicators
| State | Color | Hex |
|-------|-------|-----|
| Healthy | Green | `#5b9e2a` |
| Water stress (wilting) | Yellow-brown | `#b8943a` |
| N deficiency | Pale yellow-green | `#c8d86a` |
| Severe stress | Brown/dead | `#8b6b3a` |

### UI Colors
| Element | Color | Hex |
|---------|-------|-----|
| Grade A | Green | `#33cc33` |
| Grade B | Yellow-green | `#80cc33` |
| Grade C | Yellow | `#e6cc1a` |
| Grade D | Orange | `#e6801a` |
| Grade F | Red | `#e63333` |
| Revenue/Positive | Green | `#4dcc4d` |
| Cost/Negative | Red | `#cc4d4d` |
| Rain | Blue | `#6699cc` |
| Sun | Yellow | `#f0d040` |

## Lighting Model

**Light direction**: Top-left, ~45° azimuth, consistent across all assets. This affects:

- **Highlights**: Flat lighter accent strokes on the **top-left edges** of leaves, seed heads, and other surfaces facing the light. Use a color ~20% lighter than the base fill, at 0.4–0.6 opacity. Only apply to light-facing (left) elements — right-side elements are in relative shadow.
- **Cast shadows**: Flat semi-transparent dark ellipse (`#000000`, opacity 0.09–0.15) at the base of crops, offset toward the **bottom-right** to match the light direction. Skew with `skewX(-15)` to align with the isometric ground plane. Shadow size should scale with plant size (seedlings get tiny shadows, mature crops get larger ones).
- **Tiles**: The top-left half of a tile surface may have a slightly lighter tone than the bottom-right. This is optional and should be very subtle if used.

## Asset Specifications

### Isometric Soil Tiles
- **Size**: 64x32 pixels (isometric diamond)
- **Format**: SVG
- **Naming**: `tile_{soil_type}.svg`
- **Requirements**:
  - Diamond shape with `points="32,0 64,16 32,32 0,16"`
  - Subtle surface texture (NOT flat fill) — grain pattern for sand, cracked pattern for clay, organic matter specks for loam
  - 1px stroke in slightly darker shade for edge definition
  - Must read clearly at 100% and 50% zoom
  - Dynamic color modulation (SOM + moisture) is applied as a `modulate` overlay in code — base tile should be the "dry, medium SOM" default
  - **Isometric texture projection**: All texture overlays (dots, specks, cracks, patterns) MUST be designed in a flat 32×32 top-down coordinate space and projected onto the diamond using the affine transform `matrix(1,0.5,-1,0.5,32,0)`. This maps flat ground-plane coordinates onto the isometric surface so textures appear to lie on the tile rather than floating above it. Use a `<clipPath>` on the diamond to clip the transformed content. Structure:
    ```xml
    <clipPath id="tile">
      <polygon points="32,0 64,16 32,32 0,16"/>
    </clipPath>
    <g clip-path="url(#tile)" transform="matrix(1,0.5,-1,0.5,32,0)">
      <!-- texture elements in flat 32x32 space -->
    </g>
    ```

### Crop Sprites
- **Size**: 32x32 pixels (centered on tile, offset -8px Y)
- **Format**: SVG
- **Naming**: `{crop}_{stage}.svg` (e.g., `maize_vegetative.svg`, `wheat_mature.svg`)
- **Stages per crop**: seedling, vegetative, flowering, mature
- **Stress variants**: `{crop}_wilting.svg`, `{crop}_ndeficient.svg`
- **Requirements**:
  - Plant grows taller across stages (seedling ~8px tall, mature ~24px tall)
  - Each crop visually distinct even at vegetative stage (maize: tall single stalk + broad leaves; wheat: thin tillers; sorghum: thick stalk + seed head; rice: thin + drooping)
  - Stress variants: wilting = drooping/curled leaves; N-deficiency = pale/yellow tint
  - Transparent background
  - Must be identifiable when placed on any soil tile color
  - **Isometric perspective**: Crops grow *upward* from the isometric ground plane. The stalk rises vertically in screen space (vertical stays vertical in isometric projection). Leaves and branches must fan out along the **isometric axes** (the diamond's diagonals: top-left↔bottom-right and top-right↔bottom-left), not screen-space horizontal. This means leaf pairs should be skewed to match the tile surface angle.
  - **Transparency by growth stage**: Early stages (seedling, vegetative) must be small and sparse, leaving most of the 32×32 canvas transparent so the underlying soil tile is clearly visible. Later stages (flowering, mature) may fill more of the canvas but should never completely obscure the tile beneath. The soil should always remain partially visible at all growth stages.

### UI Icons
- **Size**: 16x16 pixels
- **Format**: SVG
- **Naming**: `icon_{name}.svg`
- **Set needed**:
  - Weather: `icon_sun.svg`, `icon_cloud.svg`, `icon_rain.svg`, `icon_storm.svg`
  - Actions: `icon_irrigate.svg`, `icon_fertilize.svg`, `icon_plant.svg`, `icon_harvest.svg`
  - Status: `icon_credits.svg`, `icon_calendar.svg`, `icon_warning.svg`

## Crops to Create

The simulation supports these crops. Each needs 4 growth stages + 2 stress variants = 6 sprites.

| Crop | Key | Visual Identity | Flower Color |
|------|-----|----------------|--------------|
| Maize | `maize` | Tall single stalk, broad paired leaves, tassel on top | Yellow tassel |
| Spring Wheat | `spring_wheat` | Thin tillers in cluster, awned seed heads | Golden heads |
| Winter Wheat | `winter_wheat` | Same as spring wheat (visually identical) | Golden heads |
| Sorghum | `sorghum` | Thick stalk, broad leaves, dense seed head on top | Brown/red head |
| Rice | `rice` | Thin stems, narrow leaves, drooping panicle | Green-gold |
| Grape | `grape` | Short woody vine with broad leaves, grape clusters | Purple clusters |

## File Organization

```
game/assets/
  tiles/
    tile_sandy.svg
    tile_organic.svg
    tile_clay.svg
    tile_selected.svg
    tile_white.svg        # overlay base
  crops/
    maize_seedling.svg
    maize_vegetative.svg
    maize_flowering.svg
    maize_mature.svg
    maize_wilting.svg
    maize_ndeficient.svg
    wheat_seedling.svg    # shared by spring/winter wheat
    wheat_vegetative.svg
    wheat_flowering.svg
    wheat_mature.svg
    wheat_wilting.svg
    wheat_ndeficient.svg
    sorghum_seedling.svg
    ... (same pattern)
  icons/
    icon_sun.svg
    icon_cloud.svg
    icon_rain.svg
    icon_storm.svg
    icon_irrigate.svg
    icon_fertilize.svg
    icon_plant.svg
    icon_harvest.svg
    icon_credits.svg
    icon_calendar.svg
    icon_warning.svg
```

## Reference Resources

**Free asset packs (for inspiration and base assets):**
- **Kenney.nl** — Free CC0 isometric game assets including farm/nature packs. Clean flat style closest to our aesthetic.
- **OpenGameArt.org** — Search "isometric farm" for CC-licensed tile sets
- **Itch.io** — Search "isometric farm tileset" for flat/minimal isometric packs

**Color and palette references:**
- **Lospec.com** — Color palette database; search "earth tones" or "agriculture"
- **Munsell Soil Color Chart** — Scientific standard for soil colors. Sandy = 10YR 6/3 (pale brown), loam = 10YR 4/3 (brown), clay = 5YR 4/4 (reddish brown)
- **Monument Valley / Alto's Adventure palettes** — Search Coolors.co for curated palettes

**Style references:**
- **Monument Valley** (ustwo games) — Clean isometric, muted palette, geometric shapes
- **Alto's Adventure** — Minimalist landscape with vivid accent colors
- **Pocket City** — Isometric city builder with clear, readable tiles
- **Stardew Valley** — Crop stage visual language (growth = height + density + color shift)

**Tools:**
- **Inkscape** — Free SVG editor with isometric grid extension (good for 64x32 tiles)
- **Figma** — Isometric plugin for vector tile design

## Quality Checklist (for all sprites)

Every submitted sprite must pass these checks:

- [ ] Valid SVG, renders correctly in browser and Godot 4
- [ ] Correct dimensions (64x32 tiles, 32x32 crops, 16x16 icons)
- [ ] Matches color palette from this guide (exact hex or perceptually close)
- [ ] Transparent background (crops and icons)
- [ ] Visually distinct from other assets at same size category
- [ ] Readable at 100% and 50% zoom
- [ ] No embedded raster images — vector paths only
- [ ] File size under 5KB per SVG
- [ ] Naming follows convention exactly

## Style Do's and Don'ts

**Do:**
- Use clean geometric shapes with minimal path points
- Add subtle texture via pattern fills or grouped micro-shapes
- Keep consistent light direction (top-left, ~45 degrees)
- Use 1-2px strokes for definition where needed
- Test on all three soil tile backgrounds before finalizing crop sprites

**Don't:**
- Use gradients (flat/matte style only)
- Add drop shadows or glow effects
- Use more than 6 colors per sprite
- Make sprites photorealistic — this is a stylized game
- Use raster textures or embedded bitmaps
