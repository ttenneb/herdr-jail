#!/bin/bash
# enforce.sh — attempt to enforce that supported agents run jailed. (Feature #2)
#
# Fires on pane.agent_detected. Herdr offers NO launch-interception hook, so
# true prevention isn't possible; this is a best-effort watchdog. When a
# supported agent is detected running OUTSIDE a jail (its process tree has no
# podman/yolo ancestor), we warn the user and offer the jailed alternative.
#
# The event payload arrives in HERDR_PLUGIN_EVENT_JSON as {"data": {...}}.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

ev="${HERDR_PLUGIN_EVENT_JSON:-}"
[ -z "$ev" ] && exit 0
have jq || exit 0

pane_id="$(printf '%s' "$ev"   | jq -r '.data.pane_id // empty')"
agent="$(printf '%s' "$ev"     | jq -r '.data.agent // .data.display_agent // empty')"
[ -z "$pane_id" ] && exit 0

# Normalize agent label to a command word (e.g. "Claude Code" -> "claude").
agent_word="$(printf '%s' "$agent" | tr '[:upper:]' '[:lower:]' | awk '{print $1}')"
is_supported_agent "$agent_word" || exit 0

# Inspect the pane's foreground process tree: is there a podman/yolo ancestor?
info="$("$HERDR" pane process-info --pane "$pane_id" 2>/dev/null || true)"
[ -z "$info" ] && exit 0

jailed="$(printf '%s' "$info" | jq -r '
  [.result.process_info.foreground_processes[]?.name] as $names
  | if ($names | any(. == "podman" or . == "podman-remote" or . == "yolo")) then "yes" else "no" end
' 2>/dev/null || echo "no")"

if [ "$jailed" = "yes" ]; then
  # Correctly jailed — nothing to do.
  exit 0
fi

# Un-jailed supported agent detected. Warn (attempt-enforce).
log "UNJAILED agent '$agent_word' detected in pane $pane_id"
"$HERDR" notification show "Agent running outside jail" \
  --body "$agent_word is running un-jailed in pane $pane_id. Run it via 'Run agent in jail' (hs.jail.run) to sandbox it." \
  --position top-right >/dev/null 2>&1 || true

# Decorate the pane row so the un-jailed state is visible in the sidebar.
"$HERDR" pane report-metadata "$pane_id" --source hs.jail --token jail=unjailed >/dev/null 2>&1 || true
