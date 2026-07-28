#!/bin/bash
# Workspace and Workspace Resource jail action; all selected choices revalidate.
here="$(cd "$(dirname "$0")" && pwd)"; . "$here/lib.sh"
notify_failure() { "$HERDR" notification show "Jail action failed" --body "$1" --position top-right >/dev/null 2>&1 || true; }
require_json_dependencies && load_plugin_context || { notify_failure "The captured plugin context is malformed."; exit 1; }
WID="${HERDR_WORKSPACE_ID:-$PLUGIN_CONTEXT_WORKSPACE_ID}"; REPO_DIR="$PLUGIN_CONTEXT_REPO_DIR"
[ -n "$WID" ] || { notify_failure "Could not determine the Checkout."; exit 1; }
[ -z "$PLUGIN_CONTEXT_WORKSPACE_ID" ] || [ -z "${HERDR_WORKSPACE_ID:-}" ] || [ "$WID" = "$PLUGIN_CONTEXT_WORKSPACE_ID" ] || exit 1
if [ -z "${HERDR_PLUGIN_ACTION_CHOICE_JSON:-}" ]; then
  args=(plugin pane open --plugin hs.jail --entrypoint jail-menu --placement overlay --focus --env "HERDR_JAIL_WS=$WID")
  [ -z "$REPO_DIR" ] || args+=(--env "HERDR_JAIL_REPO_DIR=$REPO_DIR")
  "$HERDR" "${args[@]}"; exit $?
fi
parsed="$(printf '%s' "$HERDR_PLUGIN_ACTION_CHOICE_JSON" | python3 "$here/jail-choice.py" parse 2>/dev/null)" || true
IFS=$'\t' read -r op container identity attachment_csv selected_fp extra <<<"$parsed"
[ -n "$parsed" ] && [ -z "${extra:-}" ] || { notify_failure "The selected jail choice is invalid."; exit 1; }
jf="$(mktemp)"; wf="$(mktemp)"; snap="$(mktemp)"; rows="$(mktemp)"
trap 'rm -f "$jf" "$wf" "$snap" "$rows"' EXIT
list_jails >"$jf" || { log "could not query live Podman jails"; notify_failure "Could not verify live Podman jails."; exit 1; }
"$HERDR" workspace list >"$wf" && "$HERDR" api snapshot >"$snap" || { notify_failure "Could not refresh Herdr state."; exit 1; }
python3 "$here/resource-graph.py" --workspace "$WID" --jails "$jf" --workspaces "$wf" --snapshot "$snap" >"$rows" || { notify_failure "Could not verify jail attribution."; exit 1; }
line="$(awk -F '\t' -v id="$identity" '$4 == id {print; found=1} END {if (!found) exit 1}' "$rows")" || { notify_failure "That jail is no longer attached to this Checkout."; exit 1; }
IFS=$'\t' read -r live_name jail_dir kind live_id live_attachments live_fp extra <<<"$line"
[ -z "${extra:-}" ] && [ "$live_name" = "$container" ] && [ "$live_id" = "$identity" ] && [ "$live_attachments" = "$attachment_csv" ] && [ "$live_fp" = "$selected_fp" ] || {
  log "rejected stale/replaced jail or changed attachment graph"; notify_failure "Jail attachments changed; reopen the menu before acting."; exit 1; }
# Resource child context must identify this immutable resource and retain the
# exact attachment fingerprint displayed when its menu was opened.
if printf '%s' "${HERDR_PLUGIN_CONTEXT_JSON:-}" | jq -e 'has("workspace_resource")' >/dev/null 2>&1; then
  printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -e --arg id "$identity" --arg fp "$selected_fp" '
    .workspace_resource as $r | $r.plugin_id == "hs.jail" and $r.resource_id == $id and
    $r.data.container_id == $id and ($r.data.attachments|type) == "array" and
    all($r.data.attachments[]; type == "string") and $r.data.attachment_fingerprint == $fp' >/dev/null || {
      notify_failure "That jail resource is stale; reopen its menu."; exit 1; }
fi
case "$op" in
  open) bash "$here/jail-ops.sh" open "$WID" "$container" "$jail_dir" "$kind" "$identity" "$REPO_DIR" ;;
  close) bash "$here/jail-ops.sh" close "$container" "$identity" ;;
  *) exit 1 ;;
esac
