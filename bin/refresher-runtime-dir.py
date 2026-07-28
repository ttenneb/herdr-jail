#!/usr/bin/env python3
"""Create/validate a private UID runtime directory for the refresher lock."""
import os
import stat
import sys

base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
path = os.path.join(base, f"herdr-jail-{os.getuid()}")
try:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("runtime directory is not a UID-owned real directory")
    # Do not use a group/world-writable directory as a lock namespace.
    if info.st_mode & 0o077:
        os.chmod(path, 0o700)
        info = os.lstat(path)
        if info.st_mode & 0o077:
            raise RuntimeError("runtime directory is not private")
except (OSError, RuntimeError) as error:
    print(f"[herdr-jail] unsafe refresher runtime directory: {error}", file=sys.stderr)
    raise SystemExit(1)
print(path)
