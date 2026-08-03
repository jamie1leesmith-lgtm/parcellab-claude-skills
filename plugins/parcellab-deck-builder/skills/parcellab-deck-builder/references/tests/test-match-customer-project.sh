#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../match-customer-project.sh"
fail() { echo "FAIL: $1"; exit 1; }

# Test A: exact one match (case-insensitive)
out=$(printf 'proj-1\tAcme Corp\nproj-2\tOther Co\n' | bash "$SCRIPT" "acme corp")
[ "$out" = "REUSE proj-1" ] || fail "A: expected REUSE proj-1, got: $out"

# Test B: no match
out=$(printf 'proj-1\tAcme Corp\n' | bash "$SCRIPT" "Nobody Ltd")
[ "$out" = "CREATE" ] || fail "B: expected CREATE, got: $out"

# Test C: ambiguous (duplicate names)
out=$(printf 'proj-1\tAcme Corp\nproj-2\tAcme Corp\n' | bash "$SCRIPT" "Acme Corp")
[ "$out" = "AMBIGUOUS proj-1,proj-2" ] || fail "C: expected AMBIGUOUS proj-1,proj-2, got: $out"

# Test D: empty project list -> CREATE
out=$(printf '' | bash "$SCRIPT" "Acme Corp")
[ "$out" = "CREATE" ] || fail "D: expected CREATE on empty list, got: $out"

echo "ALL TESTS PASSED"
