#!/usr/bin/env bash
# Tests for wait_for_event.sh — no network, no long sleeps.
set -uo pipefail
SCRIPT="$(cd "$(dirname "$0")/.." && pwd)/wait_for_event.sh"
fails=0

test_returns_when_a_line_is_appended() {
  local dir; dir="$(mktemp -d)"; mkdir -p "$dir/orders/01"
  : > "$dir/orders/01/events.jsonl"
  ( sleep 1; echo '{"status":"InTransit"}' >> "$dir/orders/01/events.jsonl" ) &
  local out; out="$(bash "$SCRIPT" "$dir" 0 10)"
  if ! echo "$out" | grep -q "1"; then
    echo "FAIL: expected new total 1, got: $out"; fails=1; return
  fi
  echo "PASS: returns on append"
}

test_counts_across_all_orders() {
  local dir; dir="$(mktemp -d)"
  mkdir -p "$dir/orders/01" "$dir/orders/02"
  echo '{"status":"InTransit"}' > "$dir/orders/01/events.jsonl"
  : > "$dir/orders/02/events.jsonl"
  ( sleep 1; echo '{"status":"Delivered"}' >> "$dir/orders/02/events.jsonl" ) &
  local out; out="$(bash "$SCRIPT" "$dir" 0 10)"
  if ! echo "$out" | grep -q "2"; then
    echo "FAIL: expected total 2 across orders, got: $out"; fails=1; return
  fi
  echo "PASS: counts across all orders"
}

test_times_out_quietly() {
  local dir; dir="$(mktemp -d)"; mkdir -p "$dir/orders/01"
  : > "$dir/orders/01/events.jsonl"
  local out; out="$(bash "$SCRIPT" "$dir" 0 1)"
  if ! echo "$out" | grep -q "timeout"; then
    echo "FAIL: expected timeout, got: $out"; fails=1; return
  fi
  echo "PASS: times out quietly"
}

test_missing_dir_does_not_hang() {
  local out; out="$(bash "$SCRIPT" /nonexistent-run-dir 0 1)"
  if ! echo "$out" | grep -q "timeout"; then
    echo "FAIL: expected timeout for missing dir, got: $out"; fails=1; return
  fi
  echo "PASS: missing dir times out"
}

test_returns_when_a_line_is_appended
test_counts_across_all_orders
test_times_out_quietly
test_missing_dir_does_not_hang
[ "$fails" = "0" ] && echo "ALL TESTS PASSED"
exit $fails
