#!/bin/bash
# jail-run.sh — launch a coding agent inside a yolo-jail. (Features #1 + #2)
#
# Invoked as a Herdr action. Runs in a pane context, so HERDR_PANE_ID and the
# pane's cwd are available via HERDR_PLUGIN_CONTEXT_JSON. We:
#   1. Pick the agent (arg, or $HERDR_JAIL_AGENT, default: claude).
#   2. Look for a RUNNING jail in an ancestor dir within the SAME Herdr
#      workspace. If found, prompt to reuse it (cd there) — feature #1.
#   3. Launch `yolo -- <agent>` in the pane — feature #2 (always jailed).
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

AGENT="${1:-${HERDR_JAIL_AGENT:-claude}}"
PANE="${HERDR_PANE_ID:-}"

if [ -z "$PANE" ]; then
  log "no HERDR_PANE_ID in context; cannot target a pane."
  exit 1
fi

if ! is_supported_agent "$AGENT"; then
  log "agent '$AGENT' is not in the supported list ($SUPPORTED_AGENTS); refusing to jail-run."
  exit 1
fi

# Pane cwd from context JSON.
pane_cwd=""
if [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ] && have jq; then
  pane_cwd="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.focused_pane_cwd // empty' 2>/dev/null || true)"
fi
[ -z "$pane_cwd" ] && pane_cwd="${PWD}"

# --- Feature #1: find a running jail in an ancestor dir ---
reuse_dir=""
while IFS=$'\t' read -r name hostdir; do
  [ -z "$hostdir" ] || [ "$hostdir" = "?" ] && continue
  # Is $hostdir an ancestor of (or equal to) pane_cwd, but not pane_cwd itself?
  case "$pane_cwd/" in
    "$hostdir"/*)
      if [ "$hostdir" != "$pane_cwd" ]; then
        reuse_dir="$hostdir"
        reuse_name="$name"
        break
      fi
      ;;
  esac
done < <(list_jails)

target_dir="$pane_cwd"
if [ -n "$reuse_dir" ]; then
  # Prompt via notification, then ask in-pane for confirmation. Herdr has no
  # blocking-dialog API for plugins, so we surface a notification AND print an
  # interactive prompt into the pane the agent will launch in.
  "$HERDR" notification show "Reuse parent jail?" \
    --body "A jail is running in $reuse_dir. The agent can join it instead of creating a new one." \
    --position top-right >/dev/null 2>&1 || true
  # Interactive confirm inside the pane.
  "$HERDR" pane run "$PANE" \
    "printf '\033[1;33m[herdr-jail]\033[0m A running jail exists in a parent dir:\n  %s\nJoin it instead of a new jail for %s? [Y/n] ' '$reuse_dir'; read -r _a; case \"\$_a\" in [nN]*) echo 'Using current dir.';; *) cd '$reuse_dir' && echo 'Joining parent jail.';; esac; exec yolo -- $AGENT" \
    >/dev/null 2>&1
  log "prompted to reuse parent jail at $reuse_dir (container $reuse_name)"
  exit 0
fi

# --- Feature #2: always launch through the jail ---
log "launching '$AGENT' jailed in $target_dir (pane $PANE)"
"$HERDR" pane run "$PANE" "cd '$target_dir' && exec yolo -- $AGENT" >/dev/null 2>&1
