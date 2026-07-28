#!/bin/bash
# Report the complete jail resource projection for every Checkout.
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/lib.sh"

INTERVAL="${HERDR_JAIL_REFRESH_INTERVAL:-4}"
TTL_MS=$(( (INTERVAL * 3) * 1000 ))
# Python fcntl.flock is available on both supported platforms. The helper
# opens a no-follow UID-owned regular file, takes a nonblocking advisory lock,
# and execs this process with its FD inheritable; kernel exit releases it.
if [ "${HERDR_JAIL_REFRESH_LOCKED:-}" != "1" ]; then
  lock_root="$(python3 "$here/refresher-runtime-dir.py")" || exit 1
  socket_key="${HERDR_SOCKET_PATH:-${HERDR_SESSION_ID:-default}}"
  lock_hash="$(printf '%s' "$socket_key" | cksum | awk '{print $1}')"
  exec python3 "$here/refresher-lock.py" --lock "$lock_root/refresher-${lock_hash}.lock" -- \
    bash "$0" "$@"
fi
trap 'exit 0' INT TERM

report_once() {
  local jf wf snap graph line wid resources
  jf="$(mktemp)"; wf="$(mktemp)"; snap="$(mktemp)"; graph="$(mktemp)"
  # Do not clear/report anything on discovery failure: an unavailable Podman or
  # Herdr API is unknown state, not zero jails.
  if ! list_jails >"$jf" || ! "$HERDR" workspace list >"$wf" || ! "$HERDR" api snapshot >"$snap" \
      || ! python3 "$here/resource-graph.py" --jails "$jf" --workspaces "$wf" --snapshot "$snap" >"$graph"; then
    log "resource refresh failed; retaining the last reported resources"
    rm -f "$jf" "$wf" "$snap" "$graph"
    return 1
  fi
  while IFS= read -r line; do
    wid="$(printf '%s' "$line" | jq -er '.workspace_id' 2>/dev/null)" || { rm -f "$jf" "$wf" "$snap" "$graph"; return 1; }
    resources="$(printf '%s' "$line" | jq -ec '.resources' 2>/dev/null)" || { rm -f "$jf" "$wf" "$snap" "$graph"; return 1; }
    # The resource report is replacement-style: [] explicitly clears a Checkout
    # that lost its final jail.  --file avoids shell JSON quoting.
    resource_file="$(mktemp)"; printf '%s\n' "$resources" > "$resource_file"
    "$HERDR" workspace report-resources "$wid" --plugin hs.jail --file "$resource_file" --ttl-ms "$TTL_MS" >/dev/null || {
      rm -f "$resource_file" "$jf" "$wf" "$snap" "$graph"; return 1;
    }
    rm -f "$resource_file"
    # Upgrade cleanup for former custom sidebar presentation. These clears are
    # intentionally separate from resources and harmless if already absent.
    "$HERDR" workspace report-metadata "$wid" --source hs.jail --clear-token giticon >/dev/null 2>&1 || true
    for token in jails jail1 jail2 jail3 jail4 jail5; do
      "$HERDR" workspace report-metadata "$wid" --source hs.jail --clear-token "$token" >/dev/null 2>&1 || true
    done
  done < <(jq -c '.workspaces[]' "$graph")
  rm -f "$jf" "$wf" "$snap" "$graph"
}

log "jails resource refresher started (interval ${INTERVAL}s)"
while true; do
  report_once || true
  sleep "$INTERVAL"
done
