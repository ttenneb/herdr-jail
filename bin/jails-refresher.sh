#!/bin/bash
# jails-refresher.sh — keep sidebar tokens current per workspace.
#
# Sets custom tokens rendered via [ui.sidebar.spaces]:
#   $giticon — Nerd Font branch glyph, ONLY on workspaces whose dir is a git
#              work tree (so it doesn't float on non-git workspaces)
#   $jails   — Nerd Font lock + dir-keyed jail id when the workspace has a jail
#
# Nerd Font glyphs (need a Nerd Font in the terminal):
#   GIT_ICON  = U+E0A0 (pl-branch)   LOCK_ICON = U+F023 (fa-lock)
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

INTERVAL="${HERDR_JAIL_REFRESH_INTERVAL:-4}"
TTL_MS=$(( (INTERVAL * 3) * 1000 ))
# Nerd Font glyphs built from explicit codepoints (raw bytes don't survive
# some editors/heredocs). U+E0A0 = pl-branch, U+F023 = fa-lock.
GIT_ICON="${HERDR_JAIL_GIT_ICON:-$(printf '\xee\x82\xa0')}"   # U+E0A0 pl-branch
LOCK_ICON="${HERDR_JAIL_LOCK_ICON:-$(printf '\xef\x80\xa3')}"  # U+F023 fa-lock

log "jails-refresher started (interval ${INTERVAL}s)"
while true; do
  jf="$(mktemp)"; wf="$(mktemp)"; pf="$(mktemp)"
  list_jails > "$jf" 2>/dev/null || true
  "$HERDR" workspace list > "$wf" 2>/dev/null || echo '{}' > "$wf"
  "$HERDR" pane list > "$pf" 2>/dev/null || echo '{}' > "$pf"

  while IFS=$'\t' read -r wid has_git label; do
    [ -z "$wid" ] && continue
    # git icon only where a branch actually renders (workspace dir is a git tree)
    if [ "$has_git" = "1" ]; then
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --token giticon="$GIT_ICON" --ttl-ms "$TTL_MS" >/dev/null 2>&1 || true
    else
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --clear-token giticon >/dev/null 2>&1 || true
    fi
    # jail token only when the workspace has a jail
    if [ -n "$label" ]; then
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --token jails="${LOCK_ICON} ${label}" --ttl-ms "$TTL_MS" >/dev/null 2>&1 || true
    else
      "$HERDR" workspace report-metadata "$wid" --source hs.jail \
        --clear-token jails >/dev/null 2>&1 || true
    fi
  done < <(python3 "$here/jails-status.py" --jails "$jf" --workspaces "$wf" --panes "$pf" 2>/dev/null)

  rm -f "$jf" "$wf" "$pf"
  sleep "$INTERVAL"
done
