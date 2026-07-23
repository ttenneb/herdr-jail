#!/bin/bash
# jails-refresher.sh — keep each workspace's $jails sidebar token current.
#
# Launched as a [[startup]] command for the session lifetime. Every INTERVAL
# seconds it recomputes the jail(s) per workspace and reports a 🔒<jail-id>
# token (ttl > interval so the row never flickers); workspaces with no jail get
# the token cleared. The jail id is dir-keyed (yolo container name minus the
# "yolo-" prefix), so it reads e.g. "🔒custom_flows-eec2820e".
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

INTERVAL="${HERDR_JAIL_REFRESH_INTERVAL:-4}"
TTL_MS=$(( (INTERVAL * 3) * 1000 ))

log "jails-refresher started (interval ${INTERVAL}s)"
while true; do
  jf="$(mktemp)"; wf="$(mktemp)"; pf="$(mktemp)"
  list_jails > "$jf" 2>/dev/null || true
  "$HERDR" workspace list > "$wf" 2>/dev/null || echo '{}' > "$wf"
  "$HERDR" pane list > "$pf" 2>/dev/null || echo '{}' > "$pf"

  while IFS=$'\t' read -r wid label; do
    [ -z "$wid" ] && continue
    if [ -n "$label" ]; then
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --token jails="🔒${label}" --ttl-ms "$TTL_MS" >/dev/null 2>&1 || true
    else
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --clear-token jails >/dev/null 2>&1 || true
    fi
  done < <(python3 "$here/jails-status.py" --jails "$jf" --workspaces "$wf" --panes "$pf" 2>/dev/null)

  rm -f "$jf" "$wf" "$pf"
  sleep "$INTERVAL"
done
