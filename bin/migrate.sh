#!/bin/bash
# migrate.sh — migrate an already-running, UN-jailed agent into a jail. (Manual)
#
# This is a DELIBERATE action, never fired by the watchdog: it kills the
# un-jailed agent in the current pane and relaunches it jailed with session
# resume, so the conversation continues inside the sandbox.
#
# Caveats (surfaced to the user before acting):
#   * Destructive: the running agent is stopped and restarted. Any in-flight
#     tool call at that instant is interrupted.
#   * Resume fidelity is agent-specific. Claude supports --continue; other
#     agents may not, in which case a fresh (un-resumed) jailed session starts.
#   * There was an un-jailed window before migration — this is recovery, not
#     prevention. Use PATH shims if you need true prevention.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

AGENT="${1:-${HERDR_JAIL_AGENT:-claude}}"
PANE="${HERDR_PANE_ID:-}"

[ -z "$PANE" ] && { log "no HERDR_PANE_ID; cannot migrate."; exit 1; }
is_supported_agent "$AGENT" || { log "agent '$AGENT' not supported."; exit 1; }

# Resume flag per agent. Only claude is known-good; others start fresh.
resume_args=""
case "$AGENT" in
  claude) resume_args="--continue" ;;
  *)      resume_args="" ;;
esac

# Confirm the agent really is running un-jailed in this pane before we kill it.
info="$("$HERDR" pane process-info --pane "$PANE" 2>/dev/null || true)"
if [ -n "$info" ] && have jq; then
  jailed="$(printf '%s' "$info" | jq -r '
    [.result.process_info.foreground_processes[]?.name] as $n
    | if ($n|any(.=="podman" or .=="podman-remote" or .=="yolo")) then "yes" else "no" end' 2>/dev/null || echo no)"
  if [ "$jailed" = "yes" ]; then
    log "pane $PANE already jailed; nothing to migrate."
    "$HERDR" notification show "Already jailed" \
      --body "The agent in this pane is already running inside a jail." \
      --position top-right >/dev/null 2>&1 || true
    exit 0
  fi
fi

# Warn, then interactively confirm inside the pane. We send Ctrl-C to stop the
# running agent, then exec the jailed resume command in the same pane.
"$HERDR" notification show "Migrate agent into jail?" \
  --body "$AGENT will be stopped and relaunched jailed (${resume_args:-fresh session})." \
  --position top-right >/dev/null 2>&1 || true

resume_display="${resume_args:-"(fresh session — no resume)"}"
"$HERDR" pane run "$PANE" \
  "printf '\033[1;33m[herdr-jail]\033[0m Migrate %s into a jail? This STOPS the current agent and relaunches jailed %s. [y/N] ' '$AGENT' '$resume_display'; read -r _a; case \"\$_a\" in [yY]*) exec yolo -- $AGENT $resume_args;; *) echo 'Migration cancelled.';; esac" \
  >/dev/null 2>&1

log "migration prompt sent for '$AGENT' in pane $PANE (resume: ${resume_args:-none})"
