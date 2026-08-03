#!/usr/bin/env bash
# cache-diff.sh — decide whether the local Deck Builder cache manifest is stale.
# Args: $1 = path to the OLD manifest file (one project-relative path per line,
#            as saved after the last bootstrap/refresh)
#       $2 = path to a FRESH path list (one path per line, from a live
#            DesignSync list_files call Claude just made)
# Output (stdout):
#   FRESH                 -- path sets are identical
#   STALE
#   ADDED <path>          -- one line per path present in fresh but not old
#   REMOVED <path>        -- one line per path present in old but not fresh
set -euo pipefail

OLD="${1:?old manifest path required}"
NEW="${2:?fresh path list required}"

sorted_old=$(sort "$OLD")
sorted_new=$(sort "$NEW")

if [ "$sorted_old" = "$sorted_new" ]; then
  echo "FRESH"
  exit 0
fi

echo "STALE"
comm -13 <(printf '%s\n' "$sorted_old") <(printf '%s\n' "$sorted_new") | while IFS= read -r p; do
  [ -n "$p" ] && echo "ADDED $p"
done || true
comm -23 <(printf '%s\n' "$sorted_old") <(printf '%s\n' "$sorted_new") | while IFS= read -r p; do
  [ -n "$p" ] && echo "REMOVED $p"
done || true
