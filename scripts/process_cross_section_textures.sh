#!/usr/bin/env bash
# Process raw cross-section albedo PNGs from image generation agent.
# Input:  *_raw.png files in input directory
#         Expected: soil_sandy_cross_raw.png, soil_loam_cross_raw.png,
#                   soil_clay_cross_raw.png, water_surface_raw.png
# Output: game/assets/textures/{name}_albedo.png (512x512)
#         game/assets/textures/{name}_normal.png (512x512, basic Sobel)
#
# For better normals, upload albedos to https://cpetry.github.io/NormalMap-Online/
# and replace the generated normals.
#
# Usage: ./scripts/process_cross_section_textures.sh [input_dir]
#   input_dir defaults to current directory

set -euo pipefail

INPUT_DIR="${1:-.}"
OUTPUT_DIR="game/assets/textures"

mkdir -p "$OUTPUT_DIR"

NAMES=(soil_sandy_cross soil_loam_cross soil_clay_cross water_surface)

echo "=== Processing albedos ==="
for name in "${NAMES[@]}"; do
  raw="${INPUT_DIR}/${name}_raw.png"
  if [[ ! -f "$raw" ]]; then
    echo "SKIP: $raw not found"
    continue
  fi

  # Downscale to 512x512
  magick "$raw" -resize 512x512 "${OUTPUT_DIR}/${name}_albedo.png"
  dims=$(magick identify -format '%wx%h' "${OUTPUT_DIR}/${name}_albedo.png")
  echo "  ${name}_albedo.png: ${dims}"
done

echo ""
echo "=== Generating normal maps (Sobel — replace with NormalMap-Online for better quality) ==="
for name in "${NAMES[@]}"; do
  albedo="${OUTPUT_DIR}/${name}_albedo.png"
  if [[ ! -f "$albedo" ]]; then
    echo "SKIP: $albedo not found"
    continue
  fi

  # Generate proper OpenGL normal map: R=dX, G=dY, B=1.0
  # 1. Heightmap from albedo
  magick "$albedo" -background white -alpha remove -alpha off \
    -colorspace Gray -depth 8 "/tmp/_nm_h.png"
  # 2. Flat normal base (128,128,255 = straight up)
  magick -size 512x512 xc:"#8080FF" -depth 8 "/tmp/_nm_flat.png"
  # 3. Sobel X and Y gradients
  magick "/tmp/_nm_h.png" -morphology Convolve Sobel:0 -depth 8 "/tmp/_nm_sx.png"
  magick "/tmp/_nm_h.png" -morphology Convolve Sobel:90 -depth 8 "/tmp/_nm_sy.png"
  # 4. Composite: R=Sobel_X centered, G=Sobel_Y centered, B=full blue
  magick "/tmp/_nm_flat.png" \
    \( "/tmp/_nm_sx.png" -evaluate Add 50% \) -compose CopyRed -composite \
    \( "/tmp/_nm_sy.png" -evaluate Add 50% \) -compose CopyGreen -composite \
    -alpha off \
    "${OUTPUT_DIR}/${name}_normal.png"
  rm -f /tmp/_nm_h.png /tmp/_nm_flat.png /tmp/_nm_sx.png /tmp/_nm_sy.png
  echo "  ${name}_normal.png"
done

echo ""
echo "=== Validation ==="

echo ""
echo "--- Dimensions ---"
for name in "${NAMES[@]}"; do
  for suffix in albedo normal; do
    f="${OUTPUT_DIR}/${name}_${suffix}.png"
    [[ -f "$f" ]] || continue
    dims=$(magick identify -format '%wx%h' "$f")
    status="✅"
    [[ "$dims" != "512x512" ]] && status="❌ expected 512x512"
    echo "  $(basename "$f"): ${dims} ${status}"
  done
done

echo ""
echo "--- HSV check (albedos) ---"
for name in "${NAMES[@]}"; do
  f="${OUTPUT_DIR}/${name}_albedo.png"
  [[ -f "$f" ]] || continue
  hsv=$(magick "$f" -resize 1x1! -colorspace HSV txt:- | tail -1)
  echo "  $(basename "$f"): $hsv"
done

echo ""
echo "--- Normal map blue channel (should be > 0.7) ---"
for name in "${NAMES[@]}"; do
  f="${OUTPUT_DIR}/${name}_normal.png"
  [[ -f "$f" ]] || continue
  blue=$(magick "$f" -channel B -separate -format "%[fx:mean]" info:)
  status="✅"
  (( $(echo "$blue < 0.7" | bc -l) )) && status="⚠️ low"
  echo "  $(basename "$f"): blue=${blue} ${status}"
done

echo ""
echo "--- Tiling previews ---"
PREVIEW_DIR="/tmp/cross_section_previews"
mkdir -p "$PREVIEW_DIR"
for name in "${NAMES[@]}"; do
  f="${OUTPUT_DIR}/${name}_albedo.png"
  [[ -f "$f" ]] || continue
  magick "$f" -write mpr:t +delete -size 1536x1536 tile:mpr:t \
    "${PREVIEW_DIR}/${name}_tiled.png"
  echo "  ${PREVIEW_DIR}/${name}_tiled.png"
done

echo ""
echo "Done. Review tiled previews in ${PREVIEW_DIR}/ for seam artifacts."
echo "For better normals, upload albedos to https://cpetry.github.io/NormalMap-Online/"
echo "  Sandy:  Strength 2.5, Blur 0"
echo "  Loam:   Strength 2.0, Blur 0"
echo "  Clay:   Strength 1.0, Blur 0"
echo "  Water:  Strength 1.5, Blur 1"
