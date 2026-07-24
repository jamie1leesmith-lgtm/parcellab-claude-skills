#!/usr/bin/env bash
# run-lifecycle.sh — push a timed sequence of parcelLab tracking events.
# Each NN-*.json in EVENTS_DIR is a PARTIAL event body for POST
# /v4/track/events/ (fields: event_status, location, courier,
# tracking_number) — it must NOT set event_timestamp. The driver stamps
# event_timestamp with the REAL wall-clock time at the moment each event is
# actually sent, because parcelLab always sends comms at real send time
# regardless of what event_timestamp says. Any pre-baked timestamp (future
# OR past) makes the checkpoint and its comm disagree on ordering. Success
# is HTTP 204.
# Env: EVENTS_DIR (required), GAP_SECONDS (default 120), LOG_FILE
#      (default $EVENTS_DIR/run.log), DRYRUN (default 0).
# Live mode also needs PARCELLAB_USER_ID and PARCELLAB_TOKEN.
set -euo pipefail

EVENTS_DIR="${EVENTS_DIR:?EVENTS_DIR required}"
GAP_SECONDS="${GAP_SECONDS:-120}"
LOG_FILE="${LOG_FILE:-$EVENTS_DIR/run.log}"
DRYRUN="${DRYRUN:-0}"
# Trailing slash is required; without it the API 301-redirects and drops the body.
API_URL="https://api.parcellab.com/v4/track/events/"
# GAP_SECONDS is applied BEFORE every event, including the first. The setup
# calls (order create + add_tracking, done before this script runs) trigger an
# order-confirmation comm that also processes asynchronously — firing event 1
# immediately after setup gives it no time to land first. A leading gap fixes
# this the same way the inter-event gap fixes ordering between later stages.

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"; }

if [ "$DRYRUN" != "1" ]; then
  : "${PARCELLAB_USER_ID:?PARCELLAB_USER_ID required}"
  : "${PARCELLAB_TOKEN:?PARCELLAB_TOKEN required}"
  AUTH=$(printf '%s:%s' "$PARCELLAB_USER_ID" "$PARCELLAB_TOKEN" | base64 | tr -d '\n')
fi

# Portable (bash 3.2) collection of sorted payload files.
FILES=()
while IFS= read -r line; do
  [ -n "$line" ] && FILES+=("$line")
done < <(find "$EVENTS_DIR" -maxdepth 1 -name '[0-9][0-9]-*.json' | sort)

if [ "${#FILES[@]}" -eq 0 ]; then
  log "ERROR: no NN-*.json payloads in $EVENTS_DIR"
  exit 1
fi

log "START sequence: ${#FILES[@]} events, gap=${GAP_SECONDS}s, dryrun=${DRYRUN}, endpoint=${API_URL}"
i=0
for f in "${FILES[@]}"; do
  i=$((i + 1))
  name=$(basename "$f")
  log "sleep ${GAP_SECONDS}s before event $i/${#FILES[@]}"
  sleep "$GAP_SECONDS"
  now=$(date -u +%Y-%m-%dT%H:%M:%S.000Z)
  body=$(python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
d['event_timestamp'] = sys.argv[2]
print(json.dumps(d))
" "$f" "$now")
  log "EVENT $i/${#FILES[@]} -> $name (event_timestamp=$now)"
  if [ "$DRYRUN" = "1" ]; then
    log "[dry-run] would POST $name to $API_URL"
  else
    resp=$(curl -sS -X POST "$API_URL" \
      -H "Authorization: Parcellab-API-Token $AUTH" \
      -H "Content-Type: application/json" \
      -w $'\n---HTTP %{http_code}---' \
      --data-binary "$body" 2>&1) || resp="CURL_ERROR exit=$?"
    log "RESPONSE $name: $resp"
  fi
done
log "DONE sequence complete"
