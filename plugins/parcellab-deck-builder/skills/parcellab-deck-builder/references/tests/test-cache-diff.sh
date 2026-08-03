#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../cache-diff.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "FAIL: $1"; exit 1; }

# Test A: identical sets -> FRESH
printf 'a.txt\nb.txt\n' > "$TMP/old.txt"
printf 'b.txt\na.txt\n' > "$TMP/new_same.txt"
out=$(bash "$SCRIPT" "$TMP/old.txt" "$TMP/new_same.txt")
[ "$out" = "FRESH" ] || fail "A: expected FRESH, got: $out"

# Test B: added + removed
printf 'a.txt\nb.txt\n' > "$TMP/old2.txt"
printf 'a.txt\nc.txt\n' > "$TMP/new2.txt"
out=$(bash "$SCRIPT" "$TMP/old2.txt" "$TMP/new2.txt")
echo "$out" | grep -qx "STALE" || fail "B: expected STALE line, got: $out"
echo "$out" | grep -qx "ADDED c.txt" || fail "B: expected ADDED c.txt, got: $out"
echo "$out" | grep -qx "REMOVED b.txt" || fail "B: expected REMOVED b.txt, got: $out"

# Test C: empty old manifest (first bootstrap) -> everything added
printf '' > "$TMP/old3.txt"
printf 'x.txt\ny.txt\n' > "$TMP/new3.txt"
out=$(bash "$SCRIPT" "$TMP/old3.txt" "$TMP/new3.txt")
echo "$out" | grep -qx "ADDED x.txt" || fail "C: expected ADDED x.txt, got: $out"
echo "$out" | grep -qx "ADDED y.txt" || fail "C: expected ADDED y.txt, got: $out"

echo "ALL TESTS PASSED"
