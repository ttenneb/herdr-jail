#!/bin/bash
# open-tree.sh — open the Jail Tree pane. (Feature #3 opener)
#
# An action's cwd is the plugin dir, so we can invoke the herdr CLI to open the
# declared [[panes]] entrypoint "tree" in a split.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

target="${HERDR_PANE_ID:-}"
args=(plugin pane open --plugin hs.jail --entrypoint tree --placement split --direction right --focus)
if [ -n "$target" ]; then
  args+=(--target-pane "$target")
fi

"$HERDR" "${args[@]}"
