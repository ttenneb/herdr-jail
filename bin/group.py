#!/usr/bin/env python3
"""Group running jails under Herdr workspaces for the Jail Tree pane.

Reads three inputs and prints an ANSI tree to stdout:
  --jails FILE       TSV: <container_name>\t<host_dir>   (from lib.sh list_jails)
  --workspaces JSON  `herdr workspace list` output
  --panes JSON       `herdr pane list` output

Attribution rule (fixes over-attribution of parent jails to child workspaces):
  * Each pane resolves to the DEEPEST jail whose host_dir is an ancestor-or-equal
    of the pane's cwd. That is the jail the pane actually runs in.
  * A jail is shown under a workspace only if some pane in that workspace
    resolves to it. So a parent-dir jail is attributed to the workspace whose
    panes live there, not to every descendant workspace.
  * Jails with no resolving pane are listed as orphans.
"""
import argparse
import json
import sys

C_TITLE = "\033[1m"
C_WS = "\033[1;36m"
C_DIM = "\033[2m"
C_RST = "\033[0m"


def is_ancestor_or_equal(anc: str, path: str) -> bool:
    anc = anc.rstrip("/")
    path = path.rstrip("/")
    return path == anc or path.startswith(anc + "/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jails", required=True)
    ap.add_argument("--workspaces", required=True)
    ap.add_argument("--panes", required=True)
    ap.add_argument("--interval", default="3")
    args = ap.parse_args()

    jails = []  # list of (name, host_dir)
    with open(args.jails, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] and parts[1] != "?":
                jails.append((parts[0], parts[1]))

    def load(path):
        try:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    ws_doc = load(args.workspaces)
    pane_doc = load(args.panes)

    workspaces = ws_doc.get("result", {}).get("workspaces", []) or []
    panes = pane_doc.get("result", {}).get("panes", []) or []

    ws_label = {w.get("workspace_id"): (w.get("label") or w.get("workspace_id")) for w in workspaces}

    jail_to_ws = {name: set() for name, _ in jails}
    jail_dir = {name: hd for name, hd in jails}

    for p in panes:
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        wid = p.get("workspace_id")
        if not cwd or not wid:
            continue
        best = None
        best_len = -1
        for name, hd in jails:
            if is_ancestor_or_equal(hd, cwd) and len(hd.rstrip("/")) > best_len:
                best = name
                best_len = len(hd.rstrip("/"))
        if best is not None:
            jail_to_ws[best].add(wid)

    print(f"{C_TITLE}\U0001f411 Herdr Jails{C_RST}   {C_DIM}(refresh {args.interval}s, ctrl+c to close){C_RST}\n")

    shown = set()
    any_ws = False
    for w in workspaces:
        wid = w.get("workspace_id")
        mine = [name for name, wids in jail_to_ws.items() if wid in wids]
        if not mine:
            continue
        any_ws = True
        print(f"{C_WS}▸ {ws_label.get(wid, wid)}{C_RST} {C_DIM}({wid}){C_RST}")
        for name in mine:
            shown.add(name)
            print(f"   └─ \U0001f4e6 {name}")
            print(f"        {C_DIM}{jail_dir[name]}{C_RST}")

    orphans = [(name, hd) for name, hd in jails if name not in shown]
    if orphans:
        if any_ws:
            print()
        print(f"{C_DIM}▸ (no active workspace pane){C_RST}")
        for name, hd in orphans:
            print(f"   └─ \U0001f4e6 {name}")
            print(f"        {C_DIM}{hd}{C_RST}")

    if not jails:
        print(f"  {C_DIM}No running jails.{C_RST}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
