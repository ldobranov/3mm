"""Shared Node update errors and root-owned file checks.

Both the executable helper and trust verifier import these definitions so module
launching cannot create different exception identities or a verifier import cycle.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat


class NodeUpdateError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def trusted_path(path: Path, *, directory=False, permissions=True) -> None:
    """Reject links and writable/untrusted ancestors before privileged use."""
    path = path.absolute()
    for ancestor in reversed((path, *path.parents)):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise NodeUpdateError("unsafe_path", "Node update path is a symlink")
        if permissions and (info.st_uid != 0 or info.st_mode & 0o022):
            raise NodeUpdateError("unsafe_path", "Node update path is not root-owned and protected")
        if ancestor != path and not stat.S_ISDIR(info.st_mode):
            raise NodeUpdateError("unsafe_path", "Node update ancestor is not a directory")
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not kind or (not directory and info.st_nlink != 1):
        raise NodeUpdateError("unsafe_path", "Node update path is not a private regular file/directory")


def read_small(path: Path, limit=64 * 1024) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
        raise NodeUpdateError("invalid_file", "Node update file is invalid or too large")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        value = source.read(limit + 1)
    if len(value) > limit:
        raise NodeUpdateError("invalid_file", "Node update file is too large")
    return value
