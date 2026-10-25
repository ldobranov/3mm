"""Bounded root-owned opt-in configuration, not a package/browser payload."""
from pathlib import Path
import hashlib
import json
import os
import stat


def protected_bytes(path, *, limit=65536):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("Session configuration path is untrusted")
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
            raise ValueError("Session configuration is invalid or oversized")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Session configuration exceeds bounds")
    return data


def configuration(path):
    raw = protected_bytes(path)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate session configuration field")
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=unique)
    if type(value) is not dict or type(value.get('version')) is not int or value['version'] != 1:
        raise ValueError("Session configuration version is unsupported")
    return value, hashlib.sha256(raw).hexdigest()


def unchanged(path, digest):
    try:
        return hashlib.sha256(protected_bytes(path)).hexdigest() == digest
    except (ValueError, OSError):
        return False
