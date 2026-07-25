#!/bin/bash
# jail-ops.sh — open/close operations for a jail attached to a workspace.
#
# Usage:
#   jail-ops.sh open <workspace_id> <name> <host_dir> <agent> <full_container_id> [repo_dir]
#   jail-ops.sh close <name> <full_container_id>
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

json_field() { printf '%s' "$1" | jq -er "$2" 2>/dev/null; }
notify() { "$HERDR" notification show "$1" --body "$2" --position top-right >/dev/null 2>&1 || true; }

op="${1:-}"; shift || true
case "$op" in
  close)
    jail="${1:-}"; identity="${2:-}"
    is_jail_container "$jail" || { log "close: invalid jail container"; exit 1; }
    is_container_identity "$identity" || { log "close: full immutable container ID required"; exit 1; }
    podman="$(podman_bin)" || exit 1
    log "closing jail $jail"
    if "$podman" stop "$identity" >/dev/null 2>&1; then
      notify "Jail closed" "$jail stopped."
    else
      notify "Jail close failed" "Could not stop $jail."
      exit 1
    fi
    ;;

  open)
    wid="${1:-}"; jail="${2:-}"; jail_dir="${3:-}"; kind="${4:-}"
    identity="${5:-}"; repo_dir="${6:-}"
    [ -n "$wid" ] && [ -n "$jail_dir" ] || { log "open: missing workspace or jail directory"; exit 1; }
    is_jail_container "$jail" || { log "open: invalid jail container"; exit 1; }
    is_supported_agent "$kind" || { log "open: unsupported agent kind '$kind'"; exit 1; }
    is_container_identity "$identity" || { log "open: full immutable container ID required"; exit 1; }
    require_json_dependencies || { log "open: jq and python3 required"; exit 1; }
    podman="$(podman_bin)" || exit 1
    [ -n "$repo_dir" ] || repo_dir="$jail_dir"

    # Lexically map the captured host repo beneath the verified jail mount. An
    # unrelated repo must never cause yolo to select or create another jail.
    if ! container_workdir="$(python3 - "$jail_dir" "$repo_dir" <<'PY'
import posixpath, sys
raw_base, raw_repo = sys.argv[1:]
if any(c in raw_base or c in raw_repo for c in "\t\r\n"):
    raise SystemExit(1)
base, repo = (posixpath.normpath(v) for v in (raw_base, raw_repo))
if not base.startswith("/") or not repo.startswith("/"):
    raise SystemExit(1)
try:
    if posixpath.commonpath((base, repo)) != base:
        raise SystemExit(1)
except ValueError:
    raise SystemExit(1)
rel = posixpath.relpath(repo, base)
print("/workspace" if rel == "." else "/workspace/" + rel)
PY
)"; then
      log "open: repo directory is outside the verified jail directory"
      notify "Open jail failed" "The workspace path is outside the selected jail."
      exit 1
    fi

    live_identity="$(container_identity "$jail" 2>/dev/null || true)"
    [ "$live_identity" = "$identity" ] || {
      log "open: selected container was removed or replaced"
      notify "Open jail failed" "The selected jail was removed or replaced."
      exit 1
    }

    short="${jail#yolo-}"; xxx="${short:0:3}"
    tab_id=""; left=""; right=""
    fail_open() {
      local message="$1"
      log "open: $message"
      if [ -n "$tab_id" ]; then
        "$HERDR" tab close "$tab_id" >/dev/null 2>&1 || true
      fi
      notify "Open jail failed" "$message"
      return 1
    }

    if ! create_json="$("$HERDR" tab create --workspace "$wid" --cwd "$repo_dir" --label "jail $xxx" --focus 2>/dev/null)"; then
      fail_open "Could not create a tab."
      exit 1
    fi
    left="$(json_field "$create_json" '.result.root_pane.pane_id' || true)"
    tab_id="$(json_field "$create_json" '.result.tab.tab_id' || true)"
    if [ -z "$left" ] || [ -z "$tab_id" ]; then
      fail_open "Herdr returned an invalid tab result."
      exit 1
    fi

    if ! split_json="$("$HERDR" pane split "$left" --direction right --cwd "$jail_dir" --no-focus 2>/dev/null)"; then
      fail_open "Could not split the jail tab."
      exit 1
    fi
    right="$(json_field "$split_json" '.result.pane.pane_id' || true)"
    if [ -z "$right" ]; then
      fail_open "Herdr returned an invalid split result."
      exit 1
    fi

    wait_ready() {
      local pane="$1" marker="__hj_ready_$$_${1//[^A-Za-z0-9]/_}"
      "$HERDR" pane run "$pane" "printf '%s\\n' $(shell_quote "$marker")" >/dev/null 2>&1 \
        && "$HERDR" pane wait-output "$pane" --match "$marker" --timeout 15000 >/dev/null 2>&1
    }
    if ! wait_ready "$left" || ! wait_ready "$right"; then
      fail_open "A new pane did not become ready."
      exit 1
    fi

    # Revalidate immediately before dispatch, then bind both panes to the full
    # immutable ID. No bare yolo invocation can select/create a replacement.
    live_identity="$(container_identity "$jail" 2>/dev/null || true)"
    if [ "$live_identity" != "$identity" ]; then
      fail_open "The selected jail was removed or replaced."
      exit 1
    fi

    q_podman="$(shell_quote "$podman")"; q_id="$(shell_quote "$identity")"
    q_agent_dir="$(shell_quote "$container_workdir")"; q_kind="$(shell_quote "$kind")"
    q_shell_dir="$(shell_quote "/workspace")"

    # `podman exec` does not run yolo-entrypoint, so reproduce its trusted
    # environment setup before resolving an agent or opening a shell. Quote the
    # complete inner program as one host-shell word: pane run accepts a command
    # string, and neither container paths nor the program may be re-expanded by
    # the host shell.
    bootstrap='source "$HOME/.config/yolo-user-env.sh"; eval "$(mise env -s bash)"; export PATH="$HOME/.yolo-shims:$PATH"'
    agent_script="$bootstrap; cd -- $q_agent_dir && exec $q_kind"
    shell_script="$bootstrap; cd -- $q_shell_dir && exec /bin/bash -i"
    q_agent_script="$(shell_quote "$agent_script")"
    q_shell_script="$(shell_quote "$shell_script")"
    agent_command="clear && exec $q_podman exec -it --workdir $q_agent_dir $q_id /bin/bash -lc $q_agent_script"
    shell_command="clear && exec $q_podman exec -it --workdir $q_shell_dir $q_id /bin/bash -lc $q_shell_script"

    if ! "$HERDR" pane run "$right" "$shell_command" >/dev/null 2>&1; then
      fail_open "Could not start the in-jail shell."
      exit 1
    fi
    if ! "$HERDR" pane run "$left" "$agent_command" >/dev/null 2>&1; then
      fail_open "Could not start the jailed agent."
      exit 1
    fi

    log "opened jail $jail ($identity): left=$left (agent $kind) right=$right"
    ;;

  *) log "unknown op: $op (expected open|close)"; exit 2 ;;
esac
