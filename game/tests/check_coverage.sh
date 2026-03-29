#!/usr/bin/env bash
# File-level coverage check for GDScript.
# Verifies every script in game/scripts/ has a corresponding test in game/tests/unit/.
#
# Usage: bash game/tests/check_coverage.sh [threshold]
# Default threshold: 100 (every script must have a test)

set -euo pipefail

SCRIPTS_DIR="game/scripts"
TESTS_DIR="game/tests/unit"
THRESHOLD="${1:-100}"

total=0
covered=0
missing=()

for script in "$SCRIPTS_DIR"/*.gd; do
    [ -f "$script" ] || continue
    basename=$(basename "$script" .gd)
    total=$((total + 1))

    test_file="$TESTS_DIR/test_${basename}.gd"
    if [ -f "$test_file" ]; then
        covered=$((covered + 1))
    else
        missing+=("$basename")
    fi
done

if [ "$total" -eq 0 ]; then
    echo "No scripts found in $SCRIPTS_DIR"
    exit 0
fi

pct=$((covered * 100 / total))
echo "GDScript file coverage: $covered/$total ($pct%)"

if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing tests for:"
    for m in "${missing[@]}"; do
        echo "  - $SCRIPTS_DIR/$m.gd -> $TESTS_DIR/test_$m.gd"
    done
fi

if [ "$pct" -lt "$THRESHOLD" ]; then
    echo "FAIL: coverage $pct% < threshold $THRESHOLD%"
    exit 1
fi

echo "PASS: coverage meets threshold ($THRESHOLD%)"
