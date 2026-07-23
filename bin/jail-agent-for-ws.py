#!/usr/bin/env python3
"""Given a workspace id, report its jails and the most-recent agent kind per jail.

Inputs:
  --workspace ID
  --jails FILE       TSV: <container_name>\t<host_dir>
  --snapshot JSON    `herdr api snapshot`

Output: one line per jail attributed to the workspace:
  <jail_name>\t<jail_host_dir>\t<agent_kind>
where agent_kind is the canonical kind (claude/pi/...) of the most recently
active agent pane running in that jail within this workspace, or "claude" as
the default when none is detected.

A jail is attributed to the workspace if any of the workspace's panes has a
foreground_cwd whose deepest-ancestor jail is that jail. "Most recent" = the
agent pane with the highest revision.
"""
import argparse, json, sys

# Map Herdr pane titles to canonical agent kinds (extend as needed).
TITLE_TO_KIND = {
    "Claude Code": "claude",
    "claude": "claude",
    "pi": "pi",
    "Codex": "codex",
    "Gemini": "gemini",
    "opencode": "opencode",
    "Copilot": "copilot",
}

def anc(a, p):
    a = a.rstrip("/"); p = p.rstrip("/")
    return p == a or p.startswith(a + "/")

def deepest_jail(cwd, jails):
    best, best_len = None, -1
    for name, hd in jails:
        if anc(hd, cwd) and len(hd.rstrip("/")) > best_len:
            best, best_len = (name, hd), len(hd.rstrip("/"))
    return best  # (name, hd) or None

def kind_of(pane):
    t = (pane.get("terminal_title_stripped") or "").strip()
    return TITLE_TO_KIND.get(t)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--jails", required=True)
    ap.add_argument("--snapshot", required=True)
    a = ap.parse_args()

    jails = []
    with open(a.jails, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line: continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] and parts[1] != "?":
                jails.append((parts[0], parts[1]))

    try:
        snap = json.load(open(a.snapshot, encoding="utf-8"))["result"]["snapshot"]
    except Exception:
        snap = {}
    panes = [p for p in snap.get("panes", []) if p.get("workspace_id") == a.workspace]

    # jail_name -> {"hd":..., "best_rev":-1, "kind":None}
    found = {}
    for p in panes:
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        if not cwd: continue
        dj = deepest_jail(cwd, jails)
        if not dj: continue
        name, hd = dj
        entry = found.setdefault(name, {"hd": hd, "best_rev": -1, "kind": None})
        k = kind_of(p)
        rev = p.get("revision", 0) or 0
        if k and rev > entry["best_rev"]:
            entry["best_rev"] = rev
            entry["kind"] = k

    for name, e in found.items():
        print(f"{name}\t{e['hd']}\t{e['kind'] or 'claude'}")

if __name__ == "__main__":
    sys.exit(main())
