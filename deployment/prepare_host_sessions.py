"""Provision a disabled, fixed unprivileged local host-session profile.

Installer-only operation. No application, session, permission grant, listener or
service is started here. Existing policy and account mismatches are refusals,
not requests to repair or take ownership of another identity.
"""
from __future__ import annotations

import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import tempfile

ACCOUNT = '3mm-terminal'
HOME = Path('/var/lib/3mm-terminal')
POLICY = Path('/etc/3mm-host-sessions.json')
SHELL = '/usr/sbin/nologin'


def _trusted_directory(path):
    for item in (path, *path.parents):
        info = item.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid != 0 or info.st_mode & 0o022):
            raise ValueError('Host session provisioning path is untrusted')


def _account():
    user = pwd.getpwnam(ACCOUNT)
    group = grp.getgrnam(ACCOUNT)
    if (user.pw_uid <= 0 or user.pw_gid <= 0 or user.pw_gid != group.gr_gid
            or user.pw_dir != str(HOME) or user.pw_shell != SHELL
            or set(os.getgrouplist(ACCOUNT, user.pw_gid)) != {user.pw_gid}
            or any(item.pw_uid == user.pw_uid and item.pw_name != ACCOUNT for item in pwd.getpwall())):
        raise ValueError('Dedicated host session account is unsafe')
    result = subprocess.run(['/usr/bin/passwd', '-S', ACCOUNT], check=True,
        capture_output=True, text=True, timeout=5)
    fields = result.stdout.split()
    if len(fields) < 2 or fields[:2] != [ACCOUNT, 'L']:
        raise ValueError('Dedicated host session account must remain password-locked')
    return user


def prepare():
    if os.geteuid() != 0:
        raise ValueError('Host session provisioning requires root')
    _trusted_directory(POLICY.parent)
    _trusted_directory(HOME.parent)
    try:
        pwd.getpwnam(ACCOUNT)
    except KeyError:
        try:
            grp.getgrnam(ACCOUNT)
        except KeyError:
            subprocess.run(['/usr/sbin/groupadd', '--system', ACCOUNT], check=True, timeout=10)
        subprocess.run(['/usr/sbin/useradd', '--system', '--gid', ACCOUNT,
            '--home-dir', str(HOME), '--shell', SHELL, '--no-create-home',
            '--password', '!', ACCOUNT], check=True, timeout=10)
    user = _account()
    try:
        HOME.mkdir(mode=0o700)
    except FileExistsError:
        info = HOME.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid != user.pw_uid or info.st_gid != user.pw_gid
                or info.st_mode & 0o077):
            raise ValueError('Dedicated host session home is untrusted')
    else:
        os.chown(HOME, user.pw_uid, user.pw_gid)
    # Publish only complete, synced bytes. A crash before publication leaves no
    # half-written installed policy; a concurrent prior decision wins unchanged.
    fd, temporary = tempfile.mkstemp(prefix='.host-sessions-', dir=POLICY.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(b'{"schema_version":1,"enabled":false}\n')
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        try:
            os.link(temporary, POLICY, follow_symlinks=False)
        except FileExistsError:
            pass  # Never overwrite a prior explicit root decision.
    finally:
        os.unlink(temporary)
    if POLICY.exists():
        directory = os.open(POLICY.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    from components.system_runtime.host_session_policy import read_host_session_policy
    policy = read_host_session_policy(require_enabled=False)
    return {'account': ACCOUNT, 'policy_enabled': policy.enabled,
            'application_started': False, 'service_started': False, 'grant_changed': False}


def main():
    print(json.dumps(prepare(), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
