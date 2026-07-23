#!/usr/bin/env python3
"""Per-workspace sidebar facts for the herdr-jail refresher.

Inputs:
  --jails FILE       TSV: <container_name>\t<host_dir>
  --workspaces JSON  `herdr workspace list`
  --panes JSON       `herdr pane list`

Output: one line per workspace:  <workspace_id>\t<has_git>\t<jail_label>
  jail_label : dir-keyed jail id(s) (yolo name minus "yolo-"), or "" if none
  has_git    : "1" if the workspace's primary dir is inside a git work tree,
               else "0"  (lets the caller show a branch icon only where a
               branch actually renders)

Attribution: a jail counts for the workspace whose pane resolves to it as the
deepest ancestor jail. The workspace's "primary dir" for the git check is the
cwd of its first pane.
"""
import argparse, json, os, subprocess, sys

MAX_LABEL = 28

def anc(a, p):
    a = a.rstrip("/"); p = p.rstrip("/")
    return p == a or p.startswith(a + "/")

def load(path):
    try:
        with open(path, encoding="utf-8") as fh: return json.load(fh)
    except Exception: return {}

def short(name):
    return name[5:] if name.startswith("yolo-") else name

def in_git_worktree(path):
    if not path or not os.path.isdir(path):
        return False
    try:
        r = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=3)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False

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
    first_cwd = {}
    for p in panes:
        cwd = p.get("foreground_cwd") or p.get("cwd") or ""
        wid = p.get("workspace_id")
        if not wid: continue
        first_cwd.setdefault(wid, cwd)
        if not cwd: continue
        best, best_len = None, -1
        for name, hd in jails:
            if anc(hd, cwd) and len(hd.rstrip("/")) > best_len:
                best, best_len = name, len(hd.rstrip("/"))
        if best is not None and wid in per_ws and best not in per_ws[wid]:
            per_ws[wid].append(best)

    git_cache = {}
    for wid in per_ws:
        if not wid: continue
        names = per_ws[wid]
        if names:
            label = ",".join(short(n) for n in names)
            if len(label) > MAX_LABEL:
                label = label[:MAX_LABEL - 1] + "…"
        else:
            label = ""
        cwd = first_cwd.get(wid, "")
        if cwd not in git_cache:
            git_cache[cwd] = in_git_worktree(cwd)
        has_git = "1" if git_cache[cwd] else "0"
        # label LAST: it may be empty, and trailing empty fields read cleanly
        print(f"{wid}\t{has_git}\t{label}")

if __name__ == "__main__":
    sys.exit(main())
