#!/usr/bin/env python3
"""Compute the running jail(s) per Herdr workspace, keyed by jail id.

Inputs (same sources as group.py):
  --jails FILE       TSV: <container_name>\t<host_dir>
  --workspaces JSON  `herdr workspace list`
  --panes JSON       `herdr pane list`

Output: one line per workspace:   <workspace_id>\t<label>
where <label> is a compact jail identifier for the sidebar token, or empty if
the workspace has no jail (caller clears the token). A jail counts toward the
workspace whose pane resolves to it as the deepest ancestor jail.

The jail id shown is the yolo container name with the "yolo-" prefix stripped
(i.e. "<basename>-<hash>", the dir-keyed id). If a workspace has multiple
distinct jails, they're joined with "," (rare; usually one).

Token VALUES have no length cap, but very long values may truncate visually in
the sidebar. We therefore emit the shortest unambiguous form: the basename-hash.
"""
import argparse, json, sys

MAX_LABEL = 28  # keep the sidebar row tidy; truncate with an ellipsis beyond this

def anc(a, p):
    a = a.rstrip("/"); p = p.rstrip("/")
    return p == a or p.startswith(a + "/")

def load(path):
    try:
        with open(path, encoding="utf-8") as fh: return json.load(fh)
    except Exception: return {}

def short(name):
    # yolo-<basename>-<hash> -> <basename>-<hash>
    return name[5:] if name.startswith("yolo-") else name

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

    per_ws = {w.get("workspace_id"): [] for w in ws}
    for p in panes:
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        wid = p.get("workspace_id")
        if not cwd or not wid: continue
        best, best_len = None, -1
        for name, hd in jails:
            if anc(hd, cwd) and len(hd.rstrip("/")) > best_len:
                best, best_len = name, len(hd.rstrip("/"))
        if best is not None and wid in per_ws and best not in per_ws[wid]:
            per_ws[wid].append(best)

    for wid, names in per_ws.items():
        if not wid: continue
        if names:
            label = ",".join(short(n) for n in names)
            if len(label) > MAX_LABEL:
                label = label[:MAX_LABEL - 1] + "…"
        else:
            label = ""
        print(f"{wid}\t{label}")

if __name__ == "__main__":
    sys.exit(main())
