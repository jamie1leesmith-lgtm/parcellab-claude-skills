#!/usr/bin/env bash
# Block until any order's event state advances, then exit so the conductor gets
# a turn to re-render and republish the run page.
#
# Usage: wait_for_event.sh <run_dir> [settle_seconds] [timeout_seconds]
#
# Prints the new total line count on change, or "timeout" if nothing moved.
# Always exits 0: a quiet watcher is not an error, and a non-zero exit would
# read as a failed run.
#
# Coalescing matters. Several orders push events within the same second, and
# one page update covering all of them is worth more than three in a row —
# each republish costs the conductor a turn.
#
# The settle window is the page's staleness floor: nothing reaches the reader
# faster than this. Concurrent drivers share a launch time and a gap, so their
# events land within a second or two of each other — a few seconds is enough to
# coalesce them, and the rest of a longer window is pure delay in front of the
# reader. Kept deliberately short: the page is meant to read as live.
set -uo pipefail

RUN_DIR="${1:?run_dir required}"
SETTLE="${2:-5}"
TIMEOUT="${3:-1200}"

count_lines() {
  local total=0 f
  for f in "$RUN_DIR"/orders/*/events.jsonl; do
    [ -f "$f" ] || continue
    total=$(( total + $(wc -l < "$f") ))
  done
  echo "$total"
}

start_total="$(count_lines)"
elapsed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
  sleep 1
  elapsed=$(( elapsed + 1 ))
  now="$(count_lines)"
  if [ "$now" -gt "$start_total" ]; then
    [ "$SETTLE" -gt 0 ] && sleep "$SETTLE"
    count_lines
    exit 0
  fi
done

echo "timeout"
exit 0
