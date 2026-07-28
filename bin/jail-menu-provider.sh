#!/bin/bash
# Emit aggregate Checkout choices or exact owner-resource choices.
here="$(cd "$(dirname "$0")" && pwd)"; . "$here/lib.sh"
require_json_dependencies || exit 1
load_plugin_context || { log "choices provider received malformed context"; exit 1; }
WID="${HERDR_WORKSPACE_ID:-$PLUGIN_CONTEXT_WORKSPACE_ID}"
[ -n "$WID" ] || { log "choices provider has no workspace context"; exit 1; }
[ -z "$PLUGIN_CONTEXT_WORKSPACE_ID" ] || [ -z "${HERDR_WORKSPACE_ID:-}" ] || [ "$WID" = "$PLUGIN_CONTEXT_WORKSPACE_ID" ] || exit 1
jf="$(mktemp)"; wf="$(mktemp)"; snap="$(mktemp)"; rows="$(mktemp)"
trap 'rm -f "$jf" "$wf" "$snap" "$rows"' EXIT
list_jails >"$jf" || { log "choices provider could not query Podman; could not validate every attributed jail"; exit 1; }
"$HERDR" workspace list >"$wf" || { log "choices provider could not query Herdr workspaces"; exit 1; }
"$HERDR" api snapshot >"$snap" || { log "choices provider could not query Herdr snapshot"; exit 1; }
python3 "$here/resource-graph.py" --workspace "$WID" --jails "$jf" --workspaces "$wf" --snapshot "$snap" >"$rows" || { log "choices provider could not derive complete attribution graph"; exit 1; }
# A resource invocation is accepted only for our exact resource and only when
# its context data agrees with fresh attribution. Context is a narrowing hint.
resource_id=""
if [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ] && printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -e 'has("workspace_resource")' >/dev/null 2>&1; then
  resource_id="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -er '
    .workspace_resource as $r | ($r.plugin_id == "hs.jail") and
    (($r.resource_id|type)=="string") and (($r.data|type)=="object") and
    ($r.resource_id == $r.data.container_id) and
    (($r.data.attachments|type)=="array") and all($r.data.attachments[]; type == "string") and
    (($r.data.attachment_fingerprint|type)=="string") | select(.) | $r.resource_id' 2>/dev/null)" || {
      log "resource choice has malformed or foreign resource context"; exit 1; }
  context_fp="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.workspace_resource.data.attachment_fingerprint')"
  selected="$(awk -F '\t' -v id="$resource_id" '$4 == id {print; found=1} END {if (!found) exit 1}' "$rows")" || {
      log "resource is stale or no longer attached"; exit 1; }
  [ "$(printf '%s' "$selected" | cut -f6)" = "$context_fp" ] || { log "resource attachment set changed"; exit 1; }
  printf '%s\n' "$selected" | python3 "$here/jail-choice.py" emit
else
  python3 "$here/jail-choice.py" emit <"$rows"
fi
