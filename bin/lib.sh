#!/bin/bash
# Shared helpers for the herdr-jail plugin.
#
# Herdr runs plugin commands with a MINIMAL PATH, so we discover tool
# locations explicitly and never assume `yolo`/`podman`/`jq` are on PATH.
set -euo pipefail

# Prepend common bin dirs so `command -v` can find Homebrew/Nix tools.
export PATH="/opt/homebrew/bin:/usr/local/bin:/nix/var/nix/profiles/default/bin:/usr/bin:/bin:${PATH:-}"

HERDR="${HERDR_BIN_PATH:-herdr}"

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

# jq is used for JSON parsing; fall back to python3 if absent.
json_get() {
  # json_get <jq-filter> — read JSON from stdin, apply filter.
  if have jq; then
    jq -r "$1"
  else
    python3 -c 'import sys,json; d=json.load(sys.stdin); print(__import__("subprocess"))' 2>/dev/null || true
  fi
}

# Return the container name yolo-jail would use for a given host dir.
# yolo-jail names jails: yolo-<basename>-<hash>. We can only match by the
# running container's mounted workspace, so we query podman instead of
# recomputing the hash.
podman_bin() { need podman; }

# List running yolo jails as TSV: <container_name>\t<workspace_host_dir>
# Uses the container's YOLO_HOST_DIR env label (set by yolo-jail).
list_jails() {
  local podman
  podman="$(podman_bin)" || return 0
  local names name hostdir
  names="$("$podman" ps --filter 'name=yolo-' --format '{{.Names}}' 2>/dev/null || true)"
  [ -z "$names" ] && return 0
  while IFS= read -r name; do
    [ -z "$name" ] && continue
    # Extract YOLO_HOST_DIR from the container's env.
    hostdir="$("$podman" inspect "$name" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
      | sed -n 's/^YOLO_HOST_DIR=//p' | head -1)"
    printf '%s\t%s\n' "$name" "${hostdir:-?}"
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
