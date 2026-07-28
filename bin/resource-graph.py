#!/usr/bin/env python3
"""Build the complete, validated jail-to-Checkout attachment graph.

This is the single attribution implementation used by reports and actions.  A
failure to read or validate any input is an error, never an empty graph.
"""
import hashlib
import json
import posixpath
import re
import sys
import unicodedata

CONTAINER_NAME_RE = re.compile(r"yolo-[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
CONTAINER_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[^\t\r\n]{1,120}\Z")
TITLE_TO_KIND = {"Claude Code": "claude", "claude": "claude", "pi": "pi", "Codex": "codex", "Gemini": "gemini", "opencode": "opencode", "Copilot": "copilot"}


def fail(message):
    raise ValueError(message)


def has_control(value):
    return any(unicodedata.category(char).startswith("C") for char in value)


def normal_path(value):
    if not isinstance(value, str) or not value or has_control(value):
        fail("invalid host directory")
    value = posixpath.normpath(value)
    if not value.startswith("/"):
        fail("host directory must be absolute")
    return value


def ancestor(root, path):
    return path == root or path.startswith(root.rstrip("/") + "/")


def no_duplicate_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path):
    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file, object_pairs_hook=no_duplicate_object,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        fail(f"invalid JSON input: {error}")


def parse_jails(path):
    records, names, identities, roots = [], set(), set(), set()
    try:
        source = open(path, encoding="utf-8")
    except OSError as error:
        fail(f"cannot read jail list: {error}")
    with source:
        for number, raw in enumerate(source, 1):
            fields = raw.rstrip("\n").split("\t")
            if len(fields) != 3:
                fail(f"invalid jail row {number}")
            name, directory, identity = fields
            if not CONTAINER_NAME_RE.fullmatch(name) or len(name) > 114:
                fail(f"invalid jail name on row {number}")
            if not CONTAINER_ID_RE.fullmatch(identity):
                fail(f"invalid immutable container ID on row {number}")
            directory = normal_path(directory)
            if name in names or identity in identities or directory in roots:
                fail("duplicate jail name, immutable ID, or normalized root")
            names.add(name); identities.add(identity); roots.add(directory)
            records.append({"name": name, "directory": directory, "id": identity})
    return records


def panes_from_snapshot(path):
    document = load_json(path)
    try:
        panes = document["result"]["snapshot"]["panes"]
    except (TypeError, KeyError):
        fail("snapshot is missing result.snapshot.panes")
    if not isinstance(panes, list):
        fail("snapshot panes must be an array")
    return panes


def workspace_ids(workspaces_path, panes):
    document = load_json(workspaces_path)
    try:
        workspaces = document["result"]["workspaces"]
    except (TypeError, KeyError):
        fail("workspace list is missing result.workspaces")
    if not isinstance(workspaces, list):
        fail("workspace list must be an array")
    result = set()
    for workspace in workspaces:
        wid = workspace.get("workspace_id") if isinstance(workspace, dict) else None
        if not isinstance(wid, str) or not ID_RE.fullmatch(wid) or has_control(wid):
            fail("workspace list contains invalid workspace ID")
        if wid in result:
            fail("workspace list contains duplicate workspace ID")
        result.add(wid)
    # Snapshot may race a list update. It is valid to have no panes in a
    # workspace, but a pane referring to an unknown Checkout is not safe to
    # attribute or clear.
    for pane in panes:
        if not isinstance(pane, dict):
            fail("snapshot contains non-object pane")
        wid = pane.get("workspace_id")
        if wid is not None and (not isinstance(wid, str) or not ID_RE.fullmatch(wid) or has_control(wid) or wid not in result):
            fail("snapshot pane has unknown workspace ID")
    return sorted(result, key=lambda item: item.encode("utf-8"))


def attachment_fingerprint(attachments):
    canonical = json.dumps(attachments, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build(jails_path, workspaces_path, snapshot_path):
    jails = parse_jails(jails_path)
    panes = panes_from_snapshot(snapshot_path)
    workspace_list = workspace_ids(workspaces_path, panes)
    attached = {jail["id"]: set() for jail in jails}
    # Agent choice is Checkout-local: a shared jail can have a different
    # most-recent agent in each attached Checkout.
    kinds = {}
    for pane in panes:
        cwd = pane.get("foreground_cwd") or pane.get("cwd")
        wid = pane.get("workspace_id")
        if cwd is None or wid is None:
            continue
        try:
            cwd = normal_path(cwd)
        except ValueError:
            fail("snapshot pane has invalid cwd")
        candidates = [jail for jail in jails if ancestor(jail["directory"], cwd)]
        if not candidates:
            continue
        jail = max(candidates, key=lambda item: len(item["directory"]))
        attached[jail["id"]].add(wid)
        title = pane.get("terminal_title_stripped")
        kind = TITLE_TO_KIND.get(title.strip()) if isinstance(title, str) else None
        revision = pane.get("revision", 0)
        if not isinstance(revision, int):
            fail("snapshot pane has invalid revision")
        key = (jail["id"], wid)
        if kind and revision > kinds.get(key, ("claude", -1))[1]:
            kinds[key] = (kind, revision)
    result = []
    for jail in jails:
        attachments = sorted(attached[jail["id"]], key=lambda item: item.encode("utf-8"))
        result.append({**jail, "attachments": attachments,
                       "fingerprint": attachment_fingerprint(attachments),
                       "kinds": {wid: kinds.get((jail["id"], wid), ("claude", -1))[0] for wid in attachments}})
    return workspace_list, result


def resources_for(workspace, graph):
    resources = []
    candidates = [jail for jail in sorted(graph, key=lambda item: (item["name"].encode("utf-8"), item["id"])) if workspace in jail["attachments"]]
    overflow = max(0, len(candidates) - 32)
    for jail in candidates[:32]:
        display = jail["name"].removeprefix("yolo-")
        if len(display) > 64:
            display = display[:55] + "…" + display[-8:]
        detail = jail["directory"]
        if overflow and len(resources) == 31:
            detail += f" · +{overflow} more jails omitted (Herdr limit)"
        resources.append({"resource_id": jail["id"], "label": f"🔒 {display}", "detail": detail[:256],
                          "data": {"container_name": jail["name"], "container_id": jail["id"],
                                   "attachments": jail["attachments"], "attachment_fingerprint": jail["fingerprint"]}})
    return resources


def main(argv):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--jails", required=True); parser.add_argument("--workspaces", required=True); parser.add_argument("--snapshot", required=True)
    parser.add_argument("--workspace")
    args = parser.parse_args(argv)
    workspaces, graph = build(args.jails, args.workspaces, args.snapshot)
    if args.workspace:
        if args.workspace not in workspaces: fail("requested workspace is absent")
        for jail in graph:
            if args.workspace in jail["attachments"]:
                print("\t".join((jail["name"], jail["directory"], jail["kinds"][args.workspace], jail["id"], ",".join(jail["attachments"]), jail["fingerprint"])))
    else:
        print(json.dumps({"workspaces": [{"workspace_id": wid, "resources": resources_for(wid, graph)} for wid in workspaces]}, separators=(",", ":"), ensure_ascii=False))

if __name__ == "__main__":
    try: main(sys.argv[1:])
    except ValueError as error:
        print(f"resource graph error: {error}", file=sys.stderr); sys.exit(1)
