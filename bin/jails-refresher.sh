#!/bin/bash
# jails-refresher.sh — keep each workspace's $jails sidebar token current.
#
# Launched as a [[startup]] command so it runs for the life of the Herdr
# session. Every INTERVAL seconds it recomputes running jails per workspace
# and reports a token (🔒N) with a TTL > interval so the row never flickers;
# workspaces with zero jails get the token cleared.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

INTERVAL="${HERDR_JAIL_REFRESH_INTERVAL:-4}"
TTL_MS=$(( (INTERVAL * 3) * 1000 ))   # comfortably longer than the loop

log "jails-refresher started (interval ${INTERVAL}s)"
while true; do
  jf="$(mktemp)"; wf="$(mktemp)"; pf="$(mktemp)"
  list_jails > "$jf" 2>/dev/null || true
  "$HERDR" workspace list > "$wf" 2>/dev/null || echo '{}' > "$wf"
  "$HERDR" pane list > "$pf" 2>/dev/null || echo '{}' > "$pf"

  while IFS=$'\t' read -r wid count; do
    [ -z "$wid" ] && continue
    if [ "${count:-0}" -gt 0 ]; then
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --token jails="🔒${count}" --ttl-ms "$TTL_MS" >/dev/null 2>&1 || true
    else
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --clear-token jails >/dev/null 2>&1 || true
    fi
  done < <(python3 "$here/jails-status.py" --jails "$jf" --workspaces "$wf" --panes "$pf" 2>/dev/null)

  rm -f "$jf" "$wf" "$pf"
  sleep "$INTERVAL"
done
