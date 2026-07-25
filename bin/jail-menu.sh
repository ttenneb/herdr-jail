#!/bin/bash
# jail-menu.sh — workspace jail action.
#
# New Herdr versions invoke this normal action with a selected choice in
# HERDR_PLUGIN_ACTION_CHOICE_JSON. Direct invocation (or an older Herdr without
# action choices) preserves the plugin-owned overlay picker fallback.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

notify_failure() {
  "$HERDR" notification show "Jail action failed" --body "$1" --position top-right >/dev/null 2>&1 || true
}

if ! require_json_dependencies; then
  log "jail menu requires jq and python3"
  notify_failure "The jail plugin requires jq and python3."
  exit 1
fi
if ! load_plugin_context; then
  log "malformed plugin invocation context"
  notify_failure "The captured workspace context is malformed."
  exit 1
fi

WID="${HERDR_WORKSPACE_ID:-$PLUGIN_CONTEXT_WORKSPACE_ID}"
REPO_DIR="$PLUGIN_CONTEXT_REPO_DIR"
context_wid="$PLUGIN_CONTEXT_WORKSPACE_ID"
if [ -n "$context_wid" ] && [ -n "${HERDR_WORKSPACE_ID:-}" ] && [ "$context_wid" != "$HERDR_WORKSPACE_ID" ]; then
  log "plugin invocation workspace context mismatch"
  notify_failure "The captured workspace context is inconsistent."
  exit 1
fi

# Selected invocation: fail closed unless the choice, captured workspace, live
# jail list, and fresh Herdr attribution all agree.
if [ -n "${HERDR_PLUGIN_ACTION_CHOICE_JSON:-}" ]; then
  if [ -z "$WID" ]; then
    log "choice invocation has missing or inconsistent workspace context"
    notify_failure "The captured workspace context is invalid."
    exit 1
  fi

  parsed="$(printf '%s' "$HERDR_PLUGIN_ACTION_CHOICE_JSON" | python3 "$here/jail-choice.py" parse 2>/dev/null || true)"
  if [ -z "$parsed" ]; then
    log "rejected invalid jail action choice"
    notify_failure "The selected jail choice is invalid."
    exit 1
  fi
  IFS=$'\t' read -r op container selected_identity extra <<<"$parsed"
  if [ -n "${extra:-}" ] || [ -z "$selected_identity" ] || { [ "$op" != "open" ] && [ "$op" != "close" ]; }; then
    log "rejected malformed or unsupported jail operation"
    notify_failure "The selected jail operation is unsupported."
    exit 1
  fi

  jf="$(mktemp)"; snap="$(mktemp)"; mapping="$(mktemp)"
  cleanup() { rm -f "$jf" "$snap" "$mapping"; }
  trap cleanup EXIT
  if ! list_jails >"$jf" 2>/dev/null; then
    log "could not query live Podman jails"
    notify_failure "Could not verify the live jail container."
    exit 1
  fi
  if ! "$HERDR" api snapshot >"$snap" 2>/dev/null; then
    log "could not refresh Herdr snapshot for jail choice"
    notify_failure "Could not verify that the jail still belongs to this workspace."
    exit 1
  fi
  if ! python3 "$here/jail-agent-for-ws.py" --workspace "$WID" --jails "$jf" --snapshot "$snap" >"$mapping" 2>/dev/null; then
    log "could not derive fresh jail attribution"
    notify_failure "Could not verify that the jail still belongs to this workspace."
    exit 1
  fi

  line=""
  while IFS= read -r candidate; do
    IFS=$'\t' read -r jc _rest <<<"$candidate"
    if [ "$jc" = "$container" ]; then
      live_identity="$(container_identity "$jc" 2>/dev/null || true)"
      [ "$live_identity" = "$selected_identity" ] || continue
      [ -n "$line" ] && { log "duplicate live mapping for $container"; exit 1; }
      line="$candidate"
    fi
  done <"$mapping"
  if [ -z "$line" ]; then
    log "rejected stale jail choice $op:$container for workspace $WID"
    notify_failure "That jail is no longer attached to the captured workspace."
    exit 1
  fi

  IFS=$'\t' read -r live_container jail_dir kind extra <<<"$line"
  if [ -n "${extra:-}" ] || [ "$live_container" != "$container" ] || [ -z "$jail_dir" ] || ! is_supported_agent "$kind"; then
    log "rejected invalid fresh mapping for $container"
    notify_failure "The live jail mapping is invalid."
    exit 1
  fi

  case "$op" in
    open) bash "$here/jail-ops.sh" open "$WID" "$container" "$jail_dir" "$kind" "$selected_identity" "$REPO_DIR" ;;
    close) bash "$here/jail-ops.sh" close "$container" "$selected_identity" ;;
    *) log "unknown operation after validation: $op"; exit 2 ;;
  esac
  exit $?
fi

# No choice: preserve the older/direct workflow by opening the overlay picker.
if [ -z "$WID" ]; then
  notify_failure "Could not determine the workspace."
  exit 1
fi
args=(plugin pane open --plugin hs.jail --entrypoint jail-menu --placement overlay --focus
      --env "HERDR_JAIL_WS=$WID")
[ -n "$REPO_DIR" ] && args+=(--env "HERDR_JAIL_REPO_DIR=$REPO_DIR")
"$HERDR" "${args[@]}"
