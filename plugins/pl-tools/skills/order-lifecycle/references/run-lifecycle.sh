#!/usr/bin/env bash
# run-lifecycle.sh — push a timed sequence of parcelLab tracking events
# through the parcellab CLI. No token: the CLI's OAuth session authenticates,
# and its edit-mode guard checks every payload's account before sending.
# Each NN-*.json in EVENTS_DIR is a PARTIAL event body for POST
# /v4/track/events/ (fields: event_status, location, courier,
# tracking_number) — it must NOT set event_timestamp or account. The driver
# injects both at send time:
#   - event_timestamp: REAL wall-clock now, because parcelLab always sends
#     comms at real send time regardless of what event_timestamp says. Any
#     pre-baked timestamp (future OR past) makes the checkpoint and its comm
#     disagree on ordering.
#   - account: from PARCELLAB_ACCOUNT_ID — the CLI's edit-mode guard refuses
#     raw writes whose payload carries no account, and the events API accepts
#     the extra field (verified in production 2026-08-07).
# Success is HTTP 204, which the CLI reports as empty output and exit 0.
# NEVER add --base-url: the default host serves /v4/track/events/, and
# overriding the host silently breaks the CLI's own edit-mode account lookup
# (every write then fails with a misleading 404 about child accounts).
# Env: EVENTS_DIR (required), GAP_SECONDS (default 200), LOG_FILE
#      (default $EVENTS_DIR/run.log), DRYRUN (default 0).
#      STATE_FILE (optional; unset = off). When set, one JSON object per line
#      is appended after each event: {"status","tracking_number","at","http"}.
#      The demo-environment conductor sets this so its watcher can turn event
#      progress into run-page updates without polling the log. Standalone runs
#      leave it unset and behave exactly as before.
# Live mode also needs PARCELLAB_ACCOUNT_ID (or legacy PARCELLAB_USER_ID)
# and the parcellab CLI on PATH, authenticated (parcellab auth login).
set -euo pipefail

EVENTS_DIR="${EVENTS_DIR:?EVENTS_DIR required}"
GAP_SECONDS="${GAP_SECONDS:-200}"
LOG_FILE="${LOG_FILE:-$EVENTS_DIR/run.log}"
DRYRUN="${DRYRUN:-0}"
STATE_FILE="${STATE_FILE:-}"
# CLI request path. Trailing slash is required; without it the API
# 301-redirects and drops the body.
API_PATH="/v4/track/events/"
# GAP_SECONDS is applied BEFORE every event, including the first. The setup
# calls (order create + add_tracking, done before this script runs) trigger an
# order-confirmation comm that also processes asynchronously — firing event 1
# immediately after setup gives it no time to land first. A leading gap fixes
# this the same way the inter-event gap fixes ordering between later stages.

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG_FILE"; }

ACCOUNT_ID="${PARCELLAB_ACCOUNT_ID:-${PARCELLAB_USER_ID:-}}"
if [ "$DRYRUN" != "1" ]; then
  case "$ACCOUNT_ID" in
    ''|*[!0-9]*)
      log "ERROR: PARCELLAB_ACCOUNT_ID (or legacy PARCELLAB_USER_ID) must be set to a numeric account id for live mode"
      exit 1
      ;;
  esac
  if ! command -v parcellab >/dev/null 2>&1; then
    log "ERROR: parcellab CLI not found on PATH — live mode needs it (dry runs don't)"
    exit 1
  fi
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

log "START sequence: ${#FILES[@]} events, gap=${GAP_SECONDS}s, dryrun=${DRYRUN}, endpoint=${API_PATH}, account=${ACCOUNT_ID:-unset}"
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
if sys.argv[3]:
    d['account'] = int(sys.argv[3])
print(json.dumps(d))
" "$f" "$now" "$ACCOUNT_ID")
  log "EVENT $i/${#FILES[@]} -> $name (event_timestamp=$now) (account=${ACCOUNT_ID:-unset})"
  outcome="dryrun"
  if [ "$DRYRUN" = "1" ]; then
    log "[dry-run] would POST $name to $API_PATH"
  else
    if resp=$(parcellab api request POST "$API_PATH" --data "$body" -o json 2>&1); then
      # HTTP 204 -> empty output; anything else the API returned gets logged.
      log "RESPONSE $name: OK${resp:+ $resp}"
      outcome="OK"
    else
      rc=$?
      log "RESPONSE $name: CLI_ERROR exit=$rc ${resp}"
      outcome="CLI_ERROR"
    fi
  fi
  # Machine-readable progress for the demo-environment watcher. Opt-in: with
  # STATE_FILE unset this block never runs and the driver is unchanged.
  if [ -n "$STATE_FILE" ]; then
    python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
line = {
    'status': d.get('event_status'),
    'tracking_number': d.get('tracking_number'),
    'at': sys.argv[2],
    'http': sys.argv[3],
}
with open(sys.argv[4], 'a') as fh:
    fh.write(json.dumps(line) + '\n')
" "$f" "$now" "$outcome" "$STATE_FILE"
  fi
done
log "DONE sequence complete"
