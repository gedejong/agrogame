#!/usr/bin/env bash
# Process raw leaf alpha mask PNGs from image generation agent.
# Input:  leaf_{crop}_raw.png files in current directory (white leaf on blue #0000FF background)
# Output: game/assets/textures/leaf_{crop}_alpha.png (white on transparent, exact target dimensions)
#
# Usage: ./scripts/process_leaf_masks.sh [input_dir]
#   input_dir defaults to current directory

set -euo pipefail

INPUT_DIR="${1:-.}"
OUTPUT_DIR="game/assets/textures"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$OUTPUT_DIR"

declare -A TARGETS=(
  [maize]="64 256"
  [wheat]="16 256"
  [sorghum]="64 256"
  [rice]="8 256"
  [grape]="128 128"
)

for crop in maize wheat sorghum rice grape; do
  raw="${INPUT_DIR}/leaf_${crop}_raw.png"
  if [[ ! -f "$raw" ]]; then
    echo "SKIP: $raw not found"
    continue
  fi

  read -r w h <<< "${TARGETS[$crop]}"
  echo "Processing leaf_${crop} → ${w}x${h}..."

  # Step 1: Blue-key to transparency
  magick "$raw" \
    -fuzz 15% -transparent "#0000FF" \
    "${TMP_DIR}/keyed.png"

  # Step 2: Flatten all RGB to pure white, keep alpha
  magick "${TMP_DIR}/keyed.png" \
    -channel RGB -evaluate set 100% +channel \
    "${TMP_DIR}/white.png"

  # Step 3: Trim transparent padding to tight bounding box around leaf
  magick "${TMP_DIR}/white.png" \
    -trim +repage \
    "${TMP_DIR}/trimmed.png"

  # Step 4: Resize to fit WITHIN target, preserving aspect ratio
  magick "${TMP_DIR}/trimmed.png" \
    -resize "${w}x${h}" \
    "${TMP_DIR}/resized.png"

  # Step 5: Place centered on exact target canvas with transparent background
  magick -size "${w}x${h}" xc:none \
    "${TMP_DIR}/resized.png" \
    -gravity center -composite \
    "${OUTPUT_DIR}/leaf_${crop}_alpha.png"

  actual=$(magick identify -format '%wx%h' "${OUTPUT_DIR}/leaf_${crop}_alpha.png")
  echo "  → ${OUTPUT_DIR}/leaf_${crop}_alpha.png (${actual})"
done

echo ""
echo "=== Validation ==="
for f in "${OUTPUT_DIR}"/leaf_*_alpha.png; do
  [[ -f "$f" ]] || continue
  dims=$(magick identify -format '%wx%h' "$f")
  coverage=$(magick "$f" -alpha extract -format "%[fx:mean]" info:)
  echo "$(basename "$f"): ${dims}, coverage: ${coverage}"
done
