#!/bin/bash
# jail-menu-ui.sh — interactive picker pane listing a workspace's jails.
#
# Runs as a plugin-owned overlay pane (opened by jail-menu.sh). Renders one
# entry per jail with Open/Close actions whose labels show the jail's first 3
# chars ("Open Jail XXX..."). Keyboard-driven; dispatches to jail-ops.sh.
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
. "$here/lib.sh"

WID="${HERDR_JAIL_WS:-${HERDR_WORKSPACE_ID:-}}"
REPO_DIR="${HERDR_JAIL_REPO_DIR:-}"

C_T=$'\033[1m'; C_D=$'\033[2m'; C_A=$'\033[1;36m'; C_R=$'\033[0m'; C_W=$'\033[1;33m'

# Gather this workspace's jails: TSV lines "<container>\t<host_dir>\t<kind>"
gather() {
  local jf snap
  jf="$(mktemp)"; snap="$(mktemp)"
  list_jails > "$jf" 2>/dev/null || true
  "$HERDR" api snapshot > "$snap" 2>/dev/null || echo '{}' > "$snap"
  python3 "$here/jail-agent-for-ws.py" --workspace "$WID" --jails "$jf" --snapshot "$snap" 2>/dev/null
  rm -f "$jf" "$snap"
}

draw() {
  clear 2>/dev/null || printf '\033[2J\033[H'
  printf '%s Jails — %s %s\n\n' "$C_T" "${WID:-?}" "$C_R"
  if [ "${#JAILS[@]}" -eq 0 ]; then
    printf '  %sNo running jails for this workspace.%s\n\n' "$C_D" "$C_R"
    printf '  %s[r]%s refresh   %s[q]%s close\n' "$C_A" "$C_R" "$C_A" "$C_R"
    return
  fi
  local i=1 line container dir kind short xxx
  for line in "${JAILS[@]}"; do
    IFS=$'\t' read -r container dir kind <<<"$line"
    short="${container#yolo-}"
    xxx="$(printf '%s' "$short" | cut -c1-3)"
    printf '  %s%d.%s %s  %s(%s, agent: %s)%s\n' "$C_T" "$i" "$C_R" "$short" "$C_D" "$dir" "$kind" "$C_R"
    printf '       %s[o%d]%s Open Jail %s...    %s[c%d]%s Close Jail %s...\n\n' "$C_A" "$i" "$C_R" "$xxx" "$C_W" "$i" "$C_R" "$xxx"
    i=$((i + 1))
  done
  printf '  %s[r]%s refresh   %s[q]%s close\n' "$C_A" "$C_R" "$C_A" "$C_R"
  printf '\n  %sType: o<n> to open, c<n> to close (e.g. o1), then Enter.%s\n' "$C_D" "$C_R"
}

# Load jails into the JAILS array (bash 3.2 compatible — no mapfile).
reload() {
  JAILS=()
  local _line
  while IFS= read -r _line; do
    [ -n "$_line" ] && JAILS+=("$_line")
  done < <(gather)
}

reload
while true; do
  draw
  printf '\n> '
  IFS= read -r cmd || break
  case "$cmd" in
    q|Q|"") break ;;
    r|R) reload ;;
    o[0-9]*|c[0-9]*)
      act="${cmd:0:1}"; idx="${cmd:1}"
      if [ "$idx" -ge 1 ] 2>/dev/null && [ "$idx" -le "${#JAILS[@]}" ]; then
        IFS=$'\t' read -r container dir kind <<<"${JAILS[$((idx-1))]}"
        if [ "$act" = "o" ]; then
          printf '\n%sOpening jail %s...%s\n' "$C_A" "${container#yolo-}" "$C_R"
          bash "$here/jail-ops.sh" open "$WID" "$container" "$dir" "${kind:-claude}" "$REPO_DIR"
          break   # tab created + focused; close the picker
        else
          printf '\n%sClosing jail %s...%s\n' "$C_W" "${container#yolo-}" "$C_R"
          bash "$here/jail-ops.sh" close "$container"
          sleep 1; reload
        fi
      fi
      ;;
    *) : ;;
  esac
done
