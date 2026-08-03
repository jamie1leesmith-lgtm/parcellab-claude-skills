#!/usr/bin/env bash
# match-customer-project.sh — decide how to resolve a customer's Claude Design project.
# Args: $1 = customer name to match (case-insensitive, exact)
# Stdin: TSV lines "projectId<TAB>name" — one per writable design-system project
#        (Claude extracts this from DesignSync list_projects's JSON before calling).
# Output (stdout), exactly one line:
#   REUSE <projectId>          -- exactly one case-insensitive name match
#   CREATE                     -- no match
#   AMBIGUOUS <id1>,<id2>,...  -- more than one match
set -euo pipefail

CUSTOMER="${1:?customer name required}"
CUSTOMER_LC=$(printf '%s' "$CUSTOMER" | tr '[:upper:]' '[:lower:]')

matches=()
while IFS=$'\t' read -r id name; do
  [ -z "${id:-}" ] && continue
  name_lc=$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')
  if [ "$name_lc" = "$CUSTOMER_LC" ]; then
    matches+=("$id")
  fi
done

case "${#matches[@]}" in
  0) echo "CREATE" ;;
  1) echo "REUSE ${matches[0]}" ;;
  *) IFS=','; echo "AMBIGUOUS ${matches[*]}"; IFS=' ' ;;
esac
