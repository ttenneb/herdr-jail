#!/bin/bash
# install-shims.sh — create the shim dir with a symlink per supported agent.
#
# Each symlink (claude, pi, ...) points at jail-shim, so when the shim dir is
# early on PATH, invoking the agent re-execs it jailed. Idempotent.
#
# Usage: install-shims.sh [shim_dir]   (default: ~/.herdr-jail-shims)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/lib.sh"

SHIM_DIR="${1:-$HOME/.herdr-jail-shims}"
mkdir -p "$SHIM_DIR"

for agent in $SUPPORTED_AGENTS; do
  ln -sf "$here/jail-shim" "$SHIM_DIR/$agent"
done

log "installed shims for [$SUPPORTED_AGENTS] in $SHIM_DIR"
ls -l "$SHIM_DIR"
cat <<MSG

Next steps:
  1. Point Herdr at the enforcing shell (in ~/.config/herdr/config.toml):
       [terminal]
       default_shell = "$here/herdr-jail-shell"
  2. Reload: herdr server reload-config   (or restart Herdr)
  3. New panes will auto-jail supported agents. Bypass with: YOLO_BYPASS=1 <agent>
MSG
