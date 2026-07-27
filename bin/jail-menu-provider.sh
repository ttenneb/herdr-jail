#!/bin/bash
# jail-menu-provider.sh — emit choices for the workspace jail action.
#
# stdout is exactly one version-1 PluginActionChoices JSON document. The
# selected choice is later delivered to jail-menu.sh in the environment, never
# through argv.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

require_json_dependencies || { log "choices provider requires jq and python3"; exit 1; }
load_plugin_context || { log "choices provider received malformed context"; exit 1; }

WID="${HERDR_WORKSPACE_ID:-$PLUGIN_CONTEXT_WORKSPACE_ID}"
if [ -n "$PLUGIN_CONTEXT_WORKSPACE_ID" ] && [ -n "${HERDR_WORKSPACE_ID:-}" ] \
    && [ "$PLUGIN_CONTEXT_WORKSPACE_ID" != "$HERDR_WORKSPACE_ID" ]; then
  log "choices provider workspace context mismatch"
  exit 1
fi
[ -n "$WID" ] || { log "choices provider has no workspace context"; exit 1; }

jf="$(mktemp)"; snap="$(mktemp)"; attributed="$(mktemp)"
cleanup() { rm -f "$jf" "$snap" "$attributed"; }
trap cleanup EXIT
list_jails >"$jf" 2>/dev/null || { log "choices provider could not query Podman"; exit 1; }
"$HERDR" api snapshot >"$snap" 2>/dev/null || { log "choices provider could not query Herdr"; exit 1; }
if ! python3 "$here/jail-agent-for-ws.py" --workspace "$WID" --jails "$jf" --snapshot "$snap" 2>/dev/null \
    | while IFS=$'\t' read -r container dir kind extra; do
        [ -z "${extra:-}" ] || { log "invalid attributed jail mapping"; exit 1; }
        if ! identity="$(container_identity "$container" 2>/dev/null)"; then
          log "could not resolve immutable container ID for attributed jail $container"
          exit 1
        fi
        printf '%s\t%s\t%s\t%s\n' "$container" "$dir" "$kind" "$identity"
      done >"$attributed"; then
  log "choices provider could not validate every attributed jail"
  exit 1
fi
python3 "$here/jail-choice.py" emit <"$attributed"
