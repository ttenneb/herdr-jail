#!/bin/bash
# jail-ops.sh — open/close operations for a jail attached to a workspace.
#
# Usage:
#   jail-ops.sh open  <workspace_id> <jail_container> <jail_host_dir> <agent_kind> [repo_dir]
#   jail-ops.sh close <jail_container>
#
# open  : new tab in the workspace, split vertically:
#           left  pane = agent (fresh chat) jailed, at the workspace repo dir
#           right pane = plain shell at the jail's base directory
# close : stop the podman container backing the jail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

json_field() { printf '%s' "$1" | jq -r "$2" 2>/dev/null; }

op="${1:-}"; shift || true

case "$op" in
  close)
    jail="${1:-}"
    [ -z "$jail" ] && { log "close: no jail container given"; exit 1; }
    podman="$(need podman)" || exit 1
    log "closing jail $jail"
    if "$podman" stop "$jail" >/dev/null 2>&1; then
      "$HERDR" notification show "Jail closed" --body "$jail stopped." --position top-right >/dev/null 2>&1 || true
    else
      "$HERDR" notification show "Jail close failed" --body "Could not stop $jail." --position top-right >/dev/null 2>&1 || true
      exit 1
    fi
    ;;

  open)
    wid="${1:-}"; jail="${2:-}"; jail_dir="${3:-}"; kind="${4:-claude}"; repo_dir="${5:-}"
    [ -z "$wid" ] || [ -z "$jail" ] || [ -z "$jail_dir" ] && { log "open: missing args (wid=$wid jail=$jail dir=$jail_dir)"; exit 1; }
    have jq || { log "open: jq required"; exit 1; }

    # Fall back for repo dir: workspace's base = jail_dir if not provided.
    [ -z "$repo_dir" ] && repo_dir="$jail_dir"

    short="$(printf '%s' "$jail" | sed 's/^yolo-//')"
    xxx="$(printf '%s' "$short" | cut -c1-3)"

    # Left/root pane: new tab at the workspace repo dir.
    left="$(json_field "$("$HERDR" tab create --workspace "$wid" --cwd "$repo_dir" --label "jail $xxx" --focus 2>/dev/null)" '.result.root_pane.pane_id')"
    if [ -z "$left" ] || [ "$left" = "null" ]; then
      log "open: failed to create tab in $wid"
      "$HERDR" notification show "Open jail failed" --body "Could not create a tab." --position top-right >/dev/null 2>&1 || true
      exit 1
    fi

    # Right pane: split vertically (left|right). The pane starts at the jail's
    # host dir, then we exec `yolo` to drop into an INTERACTIVE SHELL INSIDE the
    # container (lands at /workspace, the jail base).
    right="$(json_field "$("$HERDR" pane split "$left" --direction right --cwd "$jail_dir" --no-focus 2>/dev/null)" '.result.pane.pane_id')"

    # A freshly-created pane's shell may not be ready to accept typed input
    # immediately; `pane run` types text + Enter, so firing too early can drop
    # or mangle the command. We first send a marker echo and wait for it to
    # appear, which confirms the shell is at a prompt, THEN send the real
    # command. We also DON'T use `exec`: if yolo/the agent exits (e.g. a cold
    # first-run hiccup), the pane keeps its shell instead of closing.
    wait_ready() {
      # wait_ready <pane_id> — block until the pane's shell echoes a marker.
      local pane="$1" marker="__hj_ready_$$"
      "$HERDR" pane run "$pane" "printf '%s\n' $marker" >/dev/null 2>&1 || true
      "$HERDR" pane wait-output "$pane" --match "$marker" --timeout 15000 >/dev/null 2>&1 || true
    }

    # Left pane: run the agent, fresh chat, jailed, at the repo dir.
    # Bare "<kind>" (no --continue/--resume) starts a new chat.
    wait_ready "$left"
    "$HERDR" pane run "$left" "cd '$repo_dir' && clear && yolo -- $kind" >/dev/null 2>&1 || true

    # Right pane: interactive shell inside the jail. Bare `yolo` (no `--`) opens
    # an interactive jail shell at /workspace.
    if [ -n "$right" ] && [ "$right" != "null" ]; then
      wait_ready "$right"
      "$HERDR" pane run "$right" "cd '$jail_dir' && clear && yolo" >/dev/null 2>&1 || true
    fi

    log "opened jail $jail: left=$left (agent $kind) right=$right (in-jail shell)"
    ;;

  *)
    log "unknown op: $op (expected open|close)"; exit 2 ;;
esac
