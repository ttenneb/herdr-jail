#!/bin/bash
# jail-menu-provider.sh — dynamic workspace context-menu provider for jails.
#
# Two modes (both invoked by Herdr with the workspace context in env):
#
#   1. LIST  (HERDR_MENU_LIST=1): print one menu item per line as "label\targ".
#      Emits, for each jail attached to the clicked workspace:
#         "Open Jail XXX..."   arg="open:<container>"
#         "Close Jail XXX..."  arg="close:<container>"
#      (XXX = first 3 chars of the short jail id.)
#
#   2. INVOKE (--herdr-menu-arg <arg>): perform the selected op by delegating
#      to jail-ops.sh. arg is "open:<container>" or "close:<container>".
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

WID="${HERDR_WORKSPACE_ID:-}"
REPO_DIR=""
if [ -n "${HERDR_PLUGIN_CONTEXT_JSON:-}" ] && have jq; then
  [ -z "$WID" ] && WID="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.workspace_id // empty')"
  REPO_DIR="$(printf '%s' "$HERDR_PLUGIN_CONTEXT_JSON" | jq -r '.worktree.repo_root // .workspace_cwd // empty')"
fi

# --- INVOKE mode: look for --herdr-menu-arg <arg> ---
menu_arg=""
while [ $# -gt 0 ]; do
  case "$1" in
    --herdr-menu-arg) menu_arg="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

if [ -n "$menu_arg" ]; then
  op="${menu_arg%%:*}"
  container="${menu_arg#*:}"
  case "$op" in
    close)
      bash "$here/jail-ops.sh" close "$container"
      ;;
    open)
      # resolve the jail's host dir + agent kind for this workspace
      jf="$(mktemp)"; snap="$(mktemp)"
      list_jails > "$jf" 2>/dev/null || true
      "$HERDR" api snapshot > "$snap" 2>/dev/null || echo '{}' > "$snap"
      line="$(python3 "$here/jail-agent-for-ws.py" --workspace "$WID" --jails "$jf" --snapshot "$snap" 2>/dev/null | awk -F'\t' -v c="$container" '$1==c {print; exit}')"
      rm -f "$jf" "$snap"
      IFS=$'\t' read -r jc jdir jkind <<EOF
$line
EOF
      [ -z "$jdir" ] && jdir="$REPO_DIR"
      bash "$here/jail-ops.sh" open "$WID" "$container" "$jdir" "${jkind:-claude}" "$REPO_DIR"
      ;;
  esac
  exit 0
fi

# --- LIST mode (default when HERDR_MENU_LIST=1, and harmless otherwise) ---
[ -z "$WID" ] && exit 0
jf="$(mktemp)"; snap="$(mktemp)"
list_jails > "$jf" 2>/dev/null || true
"$HERDR" api snapshot > "$snap" 2>/dev/null || echo '{}' > "$snap"
python3 "$here/jail-agent-for-ws.py" --workspace "$WID" --jails "$jf" --snapshot "$snap" 2>/dev/null \
  | while IFS=$'\t' read -r container dir kind; do
      [ -z "$container" ] && continue
      short="${container#yolo-}"
      xxx="$(printf '%s' "$short" | cut -c1-3)"
      printf 'Open Jail %s...\topen:%s\n' "$xxx" "$container"
      printf 'Close Jail %s...\tclose:%s\n' "$xxx" "$container"
    done
rm -f "$jf" "$snap"
