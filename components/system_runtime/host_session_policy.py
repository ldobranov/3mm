"""Root-controlled local host-account session policy; never caller configuration.

The fixed account is not an SSH/login account and receives no platform groups.
Both discovery and execution hash the actual account as well as the policy, so
changing either requires a fresh resource review. This module changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from packages.application_sdk.session import (
    HOST_SESSION_ACCOUNT, HOST_SESSION_HOME, HOST_SESSION_PROFILE,
)

HOST_SESSION_POLICY_PATH = Path("/etc/3mm-host-sessions.json")
_MAX_POLICY_BYTES = 1024
_NONLOGIN_SHELLS = frozenset({"/usr/sbin/nologin", "/sbin/nologin", "/bin/false"})


@dataclass(frozen=True)
class HostSessionPolicy:
    enabled: bool
    sha256: str
    account: str
    uid: int
    gid: int
    home: str
    shell: str
    groups: tuple[int, ...]


def _configuration(raw):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError("Duplicate host-session policy field")
            result[name] = value
        return result

    value = json.loads(raw, object_pairs_hook=unique)
    if (type(value) is not dict or set(value) != {"schema_version", "enabled"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or type(value["enabled"]) is not bool):
        raise ValueError("Unsupported host-session policy")
    return value


def _trusted_path(path, *, directory=False, uid=0, gid=None, private=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or info.st_uid != uid
            or gid is not None and info.st_gid != gid
            or info.st_mode & (0o077 if private else 0o022)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or not directory and info.st_nlink != 1):
        raise ValueError("Host-session policy or account path is untrusted")
    return info


def _account():
    import grp
    import pwd

    account = pwd.getpwnam(HOST_SESSION_ACCOUNT)
    accounts = pwd.getpwall()
    if len(accounts) > 4096 or any(
            item.pw_uid == account.pw_uid and item.pw_name != HOST_SESSION_ACCOUNT
            for item in accounts):
        raise ValueError("Dedicated host-session account has a shared UID")
    primary = grp.getgrgid(account.pw_gid)
    groups = tuple(sorted({account.pw_gid, *(
        item.gr_gid for item in grp.getgrall() if HOST_SESSION_ACCOUNT in item.gr_mem)}))
    if (account.pw_name != HOST_SESSION_ACCOUNT or account.pw_uid <= 0 or account.pw_gid <= 0
            or primary.gr_name != HOST_SESSION_ACCOUNT or groups != (account.pw_gid,)
            or account.pw_dir != HOST_SESSION_HOME or account.pw_shell not in _NONLOGIN_SHELLS):
        raise ValueError("Dedicated unprivileged host-session account is unavailable")
    home = Path(HOST_SESSION_HOME)
    for parent in home.parents:
        _trusted_path(parent, directory=True)
    _trusted_path(home, directory=True, uid=account.pw_uid, gid=account.pw_gid, private=True)
    return account, groups


def read_host_session_policy(*, require_enabled=True):
    """Read only the fixed installed policy and Linux identity, or fail closed.

    ``require_enabled=False`` is for installer validation of a preserved disabled
    policy. It does not authorize discovery, execution, account edits or enablement.
    """
    if sys.platform != "linux" or type(require_enabled) is not bool:
        raise ValueError("Linux host-session policy is unavailable")
    path = HOST_SESSION_POLICY_PATH
    for parent in path.parents:
        _trusted_path(parent, directory=True)
    original = _trusted_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if ((opened.st_dev, opened.st_ino) != (original.st_dev, original.st_ino)
                or opened.st_uid != 0 or opened.st_mode & 0o022 or opened.st_nlink != 1
                or not stat.S_ISREG(opened.st_mode)):
            raise ValueError("Host-session policy changed while opening")
        raw = stream.read(_MAX_POLICY_BYTES + 1)
        finished = os.fstat(stream.fileno())
        if ((finished.st_dev, finished.st_ino, finished.st_ctime_ns, finished.st_mtime_ns, finished.st_size,
                finished.st_uid, finished.st_mode, finished.st_nlink) !=
                (opened.st_dev, opened.st_ino, opened.st_ctime_ns, opened.st_mtime_ns, opened.st_size,
                 opened.st_uid, opened.st_mode, opened.st_nlink)):
            raise ValueError("Host-session policy changed while reading")
    if not 1 <= len(raw) <= _MAX_POLICY_BYTES:
        raise ValueError("Host-session policy exceeds bounds")
    configuration = _configuration(raw)
    if require_enabled and not configuration["enabled"]:
        raise ValueError("Host-account sessions are disabled")
    account, groups = _account()
    identity = {"profile": HOST_SESSION_PROFILE, "configuration": configuration,
        "policy_generation": {"device": opened.st_dev, "inode": opened.st_ino,
            "changed_at_ns": opened.st_ctime_ns, "modified_at_ns": opened.st_mtime_ns,
            "content_sha256": hashlib.sha256(raw).hexdigest()},
        "account": account.pw_name, "uid": account.pw_uid, "gid": account.pw_gid,
        "home": account.pw_dir, "shell": account.pw_shell, "groups": groups}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return HostSessionPolicy(configuration["enabled"], digest, account.pw_name,
        account.pw_uid, account.pw_gid, account.pw_dir, account.pw_shell, groups)
