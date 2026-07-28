#!/usr/bin/env python3
"""Portable, exec-inherited advisory lock for one Herdr socket refresher."""
import argparse
import errno
import fcntl
import os
import stat
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--lock", required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if args.command[:1] == ["--"]:
    args.command = args.command[1:]
if not args.command:
    parser.error("a locked command is required")

# The parent directory is created/validated by refresher-runtime-dir.py. Do
# not follow a lock-file symlink, and verify the opened inode rather than a
# pre-open pathname check.
if not hasattr(os, "O_NOFOLLOW"):
    print("[herdr-jail] unsafe refresher lock: O_NOFOLLOW is unavailable", file=sys.stderr)
    raise SystemExit(1)
flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
try:
    fd = os.open(args.lock, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("lock is not a UID-owned regular file")
    if info.st_mode & 0o077:
        os.fchmod(fd, 0o600)
        if os.fstat(fd).st_mode & 0o077:
            raise RuntimeError("lock file is not private")
except (OSError, RuntimeError) as error:
    try:
        os.close(fd)
    except (NameError, OSError):
        pass
    print(f"[herdr-jail] unsafe refresher lock: {error}", file=sys.stderr)
    raise SystemExit(1)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as error:
    os.close(fd)
    if error.errno in (errno.EACCES, errno.EAGAIN):
        print("[herdr-jail] another refresher is already running for this Herdr session; exiting", file=sys.stderr)
        raise SystemExit(0)
    print(f"[herdr-jail] could not lock refresher: {error}", file=sys.stderr)
    raise SystemExit(1)
# Python makes new FDs non-inheritable by default. Retain this FD over exec so
# the kernel releases it exactly when the locked refresher process exits.
os.set_inheritable(fd, True)
os.environ["HERDR_JAIL_REFRESH_LOCKED"] = "1"
os.execvp(args.command[0], args.command)
