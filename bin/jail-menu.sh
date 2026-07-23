#!/bin/bash
# jail-menu.sh — workspace-context action: open the jail picker pane. (Feature: jail menu)
#
# Herdr manifest action titles are static and can't be dynamic per-jail, so a
# single "Jails…" action opens a plugin-owned picker pane that renders one
# Open/Close row per jail at runtime (labels show the jail's first 3 chars).
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

# Which workspace was clicked? Prefer explicit env, then the invocation context.
WID="${HERDR_WORKSPACE_ID:-}"
REPO_DIR=""
if [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ] && have jq; then
  [ -z "$WID" ] && WID="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.workspace_id // empty')"
  REPO_DIR="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.worktree.repo_root // .workspace_cwd // empty')"
fi

if [ -z "$WID" ]; then
  "$HERDR" notification show "Jails" --body "Could not determine the workspace." --position top-right >/dev/null 2>&1 || true
  exit 1
fi

# Open the picker pane as an overlay, passing the workspace id (and repo dir if known).
# Overlay panes target the ACTIVE pane and reject --workspace, so we pass the
# clicked workspace id via --env instead.
args=(plugin pane open --plugin hs.jail --entrypoint jail-menu --placement overlay --focus
      --env "HERDR_JAIL_WS=$WID")
[ -n "$REPO_DIR" ] && args+=(--env "HERDR_JAIL_REPO_DIR=$REPO_DIR")
"$HERDR" "${args[@]}"
