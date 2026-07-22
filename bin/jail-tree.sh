#!/bin/bash
# jail-tree.sh — render running yolo-jails grouped by Herdr workspace. (Feature #3)
#
# Runs as the process of a plugin-owned pane. Herdr has NO sidebar/workspace-tree
# extension API (the workspace->tab->pane hierarchy is fixed), so we render our
# own tree inside this pane. Refreshes on an interval.
#
# Data gathering is here; the (fiddly) grouping/attribution logic lives in
# group.py for clarity and correctness.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

INTERVAL="${HERDR_JAIL_TREE_INTERVAL:-3}"

render() {
  clear 2>/dev/null || printf '\033[2J\033[H'
  local jails_file ws_file pane_file
  jails_file="$(mktemp)"; ws_file="$(mktemp)"; pane_file="$(mktemp)"
  list_jails > "$jails_file" 2>/dev/null || true
  "$HERDR" workspace list > "$ws_file" 2>/dev/null || echo '{}' > "$ws_file"
  "$HERDR" pane list > "$pane_file" 2>/dev/null || echo '{}' > "$pane_file"
  python3 "$here/group.py" --jails "$jails_file" --workspaces "$ws_file" \
    --panes "$pane_file" --interval "$INTERVAL" 2>/dev/null \
    || printf '  \033[2m(jail tree unavailable)\033[0m\n'
  rm -f "$jails_file" "$ws_file" "$pane_file"
}

trap 'exit 0' INT TERM
while true; do
  render
  sleep "$INTERVAL"
done
