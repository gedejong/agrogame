#!/usr/bin/env bash
# Self-test for client_smoke.sh's log matcher (#497). Feeds synthetic logs
# through the real checks (SMOKE_CHECK_LOG mode) and asserts the verdict, so
# a matcher that passes with errors present fails CI instead of going unseen.
#
# Usage: bash game/tests/client_smoke_selftest.sh   (no backend or Godot needed)

set -uo pipefail

SMOKE="$(dirname "$0")/client_smoke.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
ESC=$'\x1B'
failures=0

# expect <name> <expected exit status> <log content>
expect() {
    printf '%s\n' "$3" >"$TMP/$1.log"
    SMOKE_CHECK_LOG="$TMP/$1.log" bash "$SMOKE" >/dev/null 2>&1
    local got=$?
    if [ "$got" -eq "$2" ]; then
        echo "ok    $1 (exit $got)"
    else
        echo "FAIL  $1: expected exit $2, got $got"
        failures=$((failures + 1))
    fi
}

expect clean 0 "[FLOW] tubes=13"
expect plain_error 1 $'[FLOW] tubes=13\nERROR: Condition "det == 0" is true.'
expect script_error 1 $'[FLOW] tubes=13\nSCRIPT ERROR: Invalid call.'
expect colour_error 1 "[FLOW] tubes=13
${ESC}[1;31mERROR:${ESC}[0m Condition \"det == 0\" is true."
expect colour_script_error 1 "[FLOW] tubes=13
${ESC}[31m${ESC}[1mSCRIPT ERROR:${ESC}[0m Invalid call."
expect osc_prefixed_error 1 "[FLOW] tubes=13
${ESC}]0;godot${ESC}\\ERROR: Condition \"det == 0\" is true."
expect colour_liveness_clean 0 "${ESC}[32m[FLOW] tubes=13${ESC}[0m"
expect no_liveness 1 "ERROR-free but never reached the cutaway"
expect error_mid_line_is_not_an_error 0 $'[FLOW] tubes=13\nlabel text mentions ERROR: harmlessly'

if [ "$failures" -gt 0 ]; then
    echo "$failures self-test case(s) failed" >&2
    exit 1
fi
echo "client_smoke matcher self-test: all cases pass"
