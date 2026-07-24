#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/../run-lifecycle.sh"
TMP="$(mktemp -d)"
EMPTY="$(mktemp -d)"
trap 'rm -rf "$TMP" "$EMPTY"' EXIT
fail() { echo "FAIL: $1"; exit 1; }

# Fixtures: three dummy event bodies out of natural order to prove sort.
echo '{"event_status":"InTransit"}'      > "$TMP/02-InTransit.json"
echo '{"event_status":"OrderProcessed"}' > "$TMP/01-OrderProcessed.json"
echo '{"event_status":"Delivered"}'      > "$TMP/03-Delivered.json"

# Test A: dry-run sends nothing, iterates all events in sorted order,
# and targets the events endpoint (not the orders endpoint).
LOG="$TMP/a.log"
EVENTS_DIR="$TMP" GAP_SECONDS=0 LOG_FILE="$LOG" DRYRUN=1 bash "$SCRIPT"
grep -q "EVENT 1/3 -> 01-OrderProcessed.json" "$LOG" || fail "A: event 1 order"
grep -q "EVENT 2/3 -> 02-InTransit.json" "$LOG" || fail "A: event 2 order"
grep -q "EVENT 3/3 -> 03-Delivered.json" "$LOG" || fail "A: event 3 order"
grep -q "DONE sequence complete" "$LOG" || fail "A: completion line"
grep -q "/v4/track/events/" "$LOG" || fail "A: must target events endpoint"
grep -q "/v4/track/orders" "$LOG" && fail "A: must NOT target orders endpoint"
grep -q "HTTP" "$LOG" && fail "A: dry-run must not call API"

# Test B: gap is applied BEFORE every event, including the first — not just
# between events. This gives setup comms (e.g. order confirmation, fired by
# order creation moments earlier) time to land before the first lifecycle
# event fires. 3 events at GAP_SECONDS=2 => 3 leading gaps => >=6s, no trailing gap.
LOG="$TMP/b.log"
start=$(date +%s)
EVENTS_DIR="$TMP" GAP_SECONDS=2 LOG_FILE="$LOG" DRYRUN=1 bash "$SCRIPT"
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -ge 6 ] || fail "B: expected >=6s (3 leading gaps), got ${elapsed}s"
[ "$elapsed" -lt 10 ] || fail "B: too slow (${elapsed}s) — extra sleep after last?"

# Test C: empty events dir exits non-zero.
if EVENTS_DIR="$EMPTY" DRYRUN=1 LOG_FILE="$EMPTY/c.log" bash "$SCRIPT"; then
  fail "C: expected non-zero exit on empty dir"
fi

# Test D: the driver must stamp event_timestamp with REAL send time,
# overriding (or ignoring) any stale/future/past value already in the file.
# This is the fix for comms and checkpoints disagreeing on ordering: comms
# always send at real wall-clock time, so event_timestamp must match it.
TMP2="$(mktemp -d)"
echo '{"event_status":"InTransit","event_timestamp":"2099-01-01T00:00:00.000Z"}' > "$TMP2/01-InTransit.json"
LOG="$TMP2/d.log"
before=$(date -u +%s)
EVENTS_DIR="$TMP2" GAP_SECONDS=0 LOG_FILE="$LOG" DRYRUN=1 bash "$SCRIPT"
after=$(date -u +%s)
line=$(grep "EVENT 1/1" "$LOG") || fail "D: no event line"
stamp=$(echo "$line" | sed -n 's/.*event_timestamp=\([^)]*\)).*/\1/p')
[ -n "$stamp" ] || fail "D: could not extract stamped event_timestamp from: $line"
stamp_epoch=$(python3 -c "
import datetime, sys
dt = datetime.datetime.strptime(sys.argv[1], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)
print(int(dt.timestamp()))
" "$stamp")
[ "$stamp_epoch" -ge "$before" ] || fail "D: stamped time before test start (not real time)"
[ "$stamp_epoch" -le "$((after + 2))" ] || fail "D: stamped time after test end (not real time)"
case "$stamp" in
  2099-*) fail "D: driver used the stale 2099 timestamp from the fixture file" ;;
esac
rm -rf "$TMP2"

echo "ALL TESTS PASSED"
