#!/usr/bin/env python3
"""Encode and strictly decode Herdr jail action choices."""

import argparse
import json
import re
import sys

CONTAINER_NAME_RE = re.compile(r"yolo-[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
CONTAINER_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
OPERATIONS = {"open", "close"}
DISPLAY_NAME_LIMIT = 32
DISPLAY_NAME_SUFFIX = 8


def valid_container_name(value):
    return isinstance(value, str) and len(value) <= 114 and CONTAINER_NAME_RE.fullmatch(value) is not None


def valid_container_id(value):
    return isinstance(value, str) and CONTAINER_ID_RE.fullmatch(value) is not None


def display_name(container_name):
    name = container_name.removeprefix("yolo-")
    if len(name) <= DISPLAY_NAME_LIMIT:
        return name
    prefix_length = DISPLAY_NAME_LIMIT - DISPLAY_NAME_SUFFIX - 1
    return f"{name[:prefix_length]}…{name[-DISPLAY_NAME_SUFFIX:]}"


def label(operation, container_name):
    verb = "Open" if operation == "open" else "Close"
    return f"{verb} {display_name(container_name)}"


def emit():
    mappings = []
    for raw in sys.stdin:
        fields = raw.rstrip("\n").split("\t")
        if len(fields) != 4 or not valid_container_name(fields[0]) or not valid_container_id(fields[3]):
            continue
        mappings.append(tuple(fields))

    # Provider order must not depend on Podman/snapshot iteration order. All
    # protocol fields are UTF-8; sorting encoded fields gives bytewise order.
    mappings.sort(key=lambda fields: tuple(field.encode("utf-8") for field in fields))
    choices = []
    seen = set()
    for container_name, _directory, _kind, container_id in mappings:
        for operation in ("open", "close"):
            choice_id = f"{operation}:{container_id}"
            if choice_id in seen:
                continue
            seen.add(choice_id)
            choices.append({
                "id": choice_id,
                "label": label(operation, container_name),
                "payload": {
                    "operation": operation,
                    "container": {"name": container_name, "id": container_id},
                },
            })
            if len(choices) == 64:
                break
        if len(choices) == 64:
            break
    json.dump({"version": 1, "choices": choices}, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


def strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def parse():
    try:
        value = json.load(
            sys.stdin,
            object_pairs_hook=strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid constant: {value}")),
        )
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        print(f"invalid choice JSON: {error}", file=sys.stderr)
        return 1

    if not isinstance(value, dict) or set(value) != {"id", "label", "payload"}:
        print("choice must contain exactly id, label, and payload", file=sys.stderr)
        return 1
    payload = value.get("payload")
    if not isinstance(payload, dict) or set(payload) != {"operation", "container"}:
        print("choice payload must contain exactly operation and container", file=sys.stderr)
        return 1
    operation, container = payload.get("operation"), payload.get("container")
    if operation not in OPERATIONS:
        print("unsupported jail operation", file=sys.stderr)
        return 1
    if not isinstance(container, dict) or set(container) != {"name", "id"}:
        print("container must contain exactly name and id", file=sys.stderr)
        return 1
    container_name, container_id = container.get("name"), container.get("id")
    if not valid_container_name(container_name) or not valid_container_id(container_id):
        print("invalid jail container", file=sys.stderr)
        return 1
    if value.get("id") != f"{operation}:{container_id}" or value.get("label") != label(operation, container_name):
        print("choice identity does not match its payload", file=sys.stderr)
        return 1

    print(f"{operation}\t{container_name}\t{container_id}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("emit", "parse"))
    args = parser.parse_args()
    return emit() if args.mode == "emit" else parse()


if __name__ == "__main__":
    raise SystemExit(main())
