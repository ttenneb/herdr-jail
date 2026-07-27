#!/bin/bash
# Shared helpers for the herdr-jail plugin.
#
# Herdr runs plugin commands with a MINIMAL PATH, so we discover tool
# locations explicitly and never assume `yolo`/`podman`/`jq`/`python3` are on PATH.
set -euo pipefail

# Prepend common bin dirs so `command -v` can find Homebrew/Nix tools.
export PATH="/opt/homebrew/bin:/usr/local/bin:/nix/var/nix/profiles/default/bin:/usr/bin:/bin:${PATH:-}"

# Herdr may atomically replace its executable while a session remains live.
# On Linux, current_exe() then ends in " (deleted)"; fall back to PATH rather
# than making every plugin API call fail until the session is restarted.
HERDR="${HERDR_BIN_PATH:-}"
if [ -z "$HERDR" ] || [ ! -x "$HERDR" ]; then
  HERDR="$(command -v herdr 2>/dev/null || true)"
fi
[ -n "$HERDR" ] && [ -x "$HERDR" ] || {
  printf '[herdr-jail] herdr executable not found\n' >&2
  return 1 2>/dev/null || exit 1
}

# Agents that yolo-jail supports (should be jailed). Keep in sync with
# yolo-jail's `agents` config valid values.
SUPPORTED_AGENTS="claude pi codex gemini opencode copilot"

log() { printf '[herdr-jail] %s\n' "$*" >&2; }

need() {
  # need <tool> — resolve a required tool or fail with a clear message.
  local tool="$1" path
  path="$(command -v "$tool" 2>/dev/null || true)"
  if [ -z "$path" ]; then
    log "required tool not found on PATH: $tool"
    return 1
  fi
  printf '%s' "$path"
}

have() { command -v "$1" >/dev/null 2>&1; }

require_json_dependencies() {
  need jq >/dev/null && need python3 >/dev/null
}

# Parse invocation context once and expose validated fields. A present context
# must be valid; callers must not silently fall back around malformed JSON.
load_plugin_context() {
  PLUGIN_CONTEXT_WORKSPACE_ID=""
  PLUGIN_CONTEXT_REPO_DIR=""
  [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ] || return 0

  local filter='def repo:
    ((if ((.worktree? | type) == "object") then
        (.worktree.checkout_path? // .worktree.repo_root?)
      else null end)
      // .workspace_cwd? // null);
    type == "object"
      and ((.workspace_id? | type) == "string")
      and ((.workspace_id | length) > 0)
      and ((.workspace_id | test("[\\t\\r\\n]")) | not)
      and ((repo == null) or (((repo | type) == "string")
        and ((repo | test("[\\t\\r\\n]")) | not)))'
  printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -e "$filter" >/dev/null 2>&1 || return 1
  PLUGIN_CONTEXT_WORKSPACE_ID="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.workspace_id')"
  PLUGIN_CONTEXT_REPO_DIR="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '
    (if ((.worktree? | type) == "object") then
       (.worktree.checkout_path? // .worktree.repo_root?)
     else null end)
      // .workspace_cwd? // empty')"
}

# Return the container name yolo-jail would use for a given host dir.
# yolo-jail names jails: yolo-<basename>-<hash>. We can only match by the
# running container's mounted workspace, so we query podman instead of
# recomputing the hash.
podman_bin() {
  if [ -n "${PODMAN_BIN_PATH:-}" ]; then
    [ -x "$PODMAN_BIN_PATH" ] || { log "PODMAN_BIN_PATH is not executable"; return 1; }
    printf '%s' "$PODMAN_BIN_PATH"
  else
    need podman
  fi
}

# List running yolo jails as TSV: <container_name>\t<workspace_host_dir>
# Uses the container's YOLO_HOST_DIR env label (set by yolo-jail).
list_jails() {
  local podman
  podman="$(podman_bin)" || return 1
  local names name hostdir inspect_env
  if ! names="$("$podman" ps --filter 'name=yolo-' --format '{{.Names}}' 2>/dev/null)"; then
    log "podman ps failed while listing jails"
    return 1
  fi
  [ -z "$names" ] && return 0
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    # Extract YOLO_HOST_DIR from the container's env. Discovery is an
    # integrity boundary: an inspect error or absent host mapping fails the
    # whole query rather than masquerading as an empty jail list.
    if ! inspect_env="$("$podman" inspect "$name" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null)"; then
      log "podman inspect failed for $name"
      return 1
    fi
    hostdir="$(printf '%s\n' "$inspect_env" | sed -n 's/^YOLO_HOST_DIR=//p' | head -1)"
    if [ -z "$hostdir" ]; then
      log "podman inspect returned no YOLO_HOST_DIR for $name"
      return 1
    fi
    printf '%s\t%s\n' "$name" "$hostdir"
  done <<EOF
$names
EOF
}

# Is a supported agent? (arg = command word)
is_supported_agent() {
  local a="$1" s
  for s in $SUPPORTED_AGENTS; do
    [ "$a" = "$s" ] && return 0
  done
  return 1
}

is_jail_container() {
  [ "${#1}" -le 114 ] && [[ "$1" =~ ^yolo-[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]
}

is_container_identity() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]]
}

container_identity() {
  local podman identity
  podman="$(podman_bin)" || return 1
  identity="$("$podman" inspect "$1" --format '{{.Id}}' 2>/dev/null)" || return 1
  is_container_identity "$identity" || return 1
  printf '%s' "$identity"
}

# Quote one string as a shell word for `herdr pane run`, whose API accepts a
# command string rather than an argv array.
shell_quote() {
  printf "'%s'" "${1//\'/\'\\\'\'}"
}
