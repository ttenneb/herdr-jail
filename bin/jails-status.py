#!/usr/bin/env python3
"""Compute running-jail count per Herdr workspace.

Inputs (same sources as group.py):
  --jails FILE       TSV: <container_name>\t<host_dir>
  --workspaces JSON  `herdr workspace list`
  --panes JSON       `herdr pane list`

Output: one line per workspace that has >=1 jail:   <workspace_id>\t<count>
Workspaces with zero jails are emitted with count 0 (so the caller can CLEAR
their token). A jail counts toward the workspace whose pane resolves to it as
the deepest ancestor jail — same attribution rule as the jail tree.
"""
import argparse, json, sys

def anc(a, p):
    a = a.rstrip("/"); p = p.rstrip("/")
    return p == a or p.startswith(a + "/")

def load(path):
    try:
        with open(path, encoding="utf-8") as fh: return json.load(fh)
    except Exception: return {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jails", required=True)
    ap.add_argument("--workspaces", required=True)
    ap.add_argument("--panes", required=True)
    a = ap.parse_args()

    jails = []
    with open(a.jails, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line: continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] and parts[1] != "?":
                jails.append((parts[0], parts[1]))

    ws = load(a.workspaces).get("result", {}).get("workspaces", []) or []
    panes = load(a.panes).get("result", {}).get("panes", []) or []

    # jail -> set(workspace_id) via deepest-ancestor pane resolution
    counts = {w.get("workspace_id"): set() for w in ws}
    for p in panes:
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        wid = p.get("workspace_id")
        if not cwd or not wid: continue
        best, best_len = None, -1
        for name, hd in jails:
            if anc(hd, cwd) and len(hd.rstrip("/")) > best_len:
                best, best_len = name, len(hd.rstrip("/"))
        if best is not None and wid in counts:
            counts[wid].add(best)

    for wid, s in counts.items():
        if wid:
            print(f"{wid}\t{len(s)}")

if __name__ == "__main__":
    sys.exit(main())
