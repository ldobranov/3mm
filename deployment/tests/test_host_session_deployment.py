"""Fixed-account provisioning and delivery checks, never live users or systemd."""
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_host_worker_has_distinct_fixed_account_home_and_cleanup_boundary():
    unit = (ROOT/'deployment/systemd/3mm-host-session-worker@.service').read_text()
    for setting in (
        'User=3mm-terminal', 'Group=3mm-terminal',
        'WorkingDirectory=/var/lib/3mm-terminal',
        'ReadWritePaths=/var/lib/3mm-terminal',
        'Environment=THREE_MM_SESSION_PROFILE=host_account_session_v1',
        'NoNewPrivileges=yes', 'CapabilityBoundingSet=\n', 'AmbientCapabilities=\n',
        'PrivateNetwork=yes', 'PrivateDevices=yes', 'ProtectSystem=strict',
        'RestrictAddressFamilies=AF_UNIX', 'RestrictNamespaces=yes', 'RestrictSUIDSGID=yes',
        'MemoryMax=128M', 'TasksMax=16', 'RuntimeMaxSec=900',
        'KillMode=control-group', 'SendSIGKILL=yes', 'BindsTo=3mm-core.service',
        'Restart=no', 'StandardInput=socket', 'StandardError=null',
        '/tmp:rw,nosuid,nodev,size=64M', '/var/tmp:rw,nosuid,nodev,size=16M',
    ):
        assert setting in unit
    assert 'EnvironmentFile=' not in unit and 'SupplementaryGroups=' not in unit
    # ProtectSystem remounts /etc read-only without binding the policy's inode;
    # an atomic root replacement must remain visible to the worker watchdog.
    assert '/etc/3mm-host-sessions.json' not in unit
    assert 'DynamicUser=' not in unit
    assert '/opt/3mm-host-session-worker/current/service.pyz' in unit
    assert all(path in unit for path in ('-/etc/3mm ', '-/var/lib/3mm ', '-/run/3mm ',
        '-/run/dbus ', '-/run/systemd/private ', '-/root'))
    isolated = (ROOT/'deployment/systemd/3mm-session-worker@.service').read_text()
    assert 'DynamicUser=yes' in isolated and 'ProtectHome=yes' in isolated
    assert 'host_account_session_v1' not in isolated and '3mm-terminal' not in isolated


def test_host_socket_is_core_only_and_installer_never_enables_profile_or_listener():
    unit = (ROOT/'deployment/systemd/3mm-host-session-worker.socket').read_text()
    for setting in ('ListenStream=/run/3mm-sessions/host-provider.sock',
        'SocketUser=root', 'SocketGroup=3mm', 'SocketMode=0660', 'DirectoryMode=0755',
        'Accept=yes', 'MaxConnections=4', 'PartOf=3mm-core.service', 'WantedBy=3mm-core.service'):
        assert setting in unit
    installer = (ROOT/'deployment/install-systemd.sh').read_text()
    assert 'service_component host-session-worker bootstrap' in installer
    assert '-m deployment.prepare_host_sessions' in installer
    assert '3mm-host-session-worker@*.service' in installer
    assert 'systemctl enable --now 3mm-host-session-worker' not in installer
    assert 'upsert_environment THREE_MM_LOCAL_SESSIONS' not in installer
    assert '"enabled":true' not in installer


def test_independent_host_component_control_stops_only_its_listener_and_workers(monkeypatch):
    from deployment import service_component
    calls = []
    monkeypatch.setattr(service_component.subprocess, 'run', lambda command, **kwargs: calls.append(command))
    control = service_component.ServiceControl('host-session-worker')
    control.stop()
    assert calls == [
        ['/usr/bin/systemctl', 'stop', '3mm-host-session-worker.socket'],
        ['/usr/bin/systemctl', 'stop', '3mm-host-session-worker@*.service']]
    calls.clear(); control.start()
    assert calls == [
        ['/usr/bin/systemctl', 'reset-failed', '3mm-host-session-worker.socket'],
        ['/usr/bin/systemctl', 'start', '3mm-host-session-worker.socket']]


@pytest.fixture
def provisioning(tmp_path, monkeypatch):
    pytest.importorskip('pwd')
    from deployment import prepare_host_sessions as helper
    from components.system_runtime import host_session_policy as policy
    home = tmp_path/'terminal-home'
    file = tmp_path/'host-sessions.json'
    user = SimpleNamespace(pw_name=helper.ACCOUNT, pw_uid=max(1, os.getuid()),
        pw_gid=max(1, os.getgid()), pw_dir=str(home), pw_shell=helper.SHELL)
    created = {'user': False, 'group': False}
    calls = []
    def lookup_user(name):
        assert name == helper.ACCOUNT
        if not created['user']:raise KeyError(name)
        return user
    def lookup_group(name):
        assert name == helper.ACCOUNT
        if not created['group']:raise KeyError(name)
        return SimpleNamespace(gr_gid=user.pw_gid)
    def run(command, **kwargs):
        calls.append(command)
        if command[0].endswith('groupadd'):created['group'] = True
        elif command[0].endswith('useradd'):created['user'] = True
        return SimpleNamespace(stdout=helper.ACCOUNT+' L 01/01/2026 0 99999 7 -1\n')
    def read_policy(*, require_enabled):
        assert require_enabled is False
        info = file.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Untrusted policy')
        value = policy._configuration(file.read_bytes())
        return SimpleNamespace(enabled=value['enabled'])
    monkeypatch.setattr(helper, 'HOME', home)
    monkeypatch.setattr(helper, 'POLICY', file)
    monkeypatch.setattr(helper.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(helper.os, 'chown', lambda *args: None)
    monkeypatch.setattr(helper.os, 'getgrouplist', lambda *args: [user.pw_gid])
    monkeypatch.setattr(helper.pwd, 'getpwnam', lookup_user)
    monkeypatch.setattr(helper.pwd, 'getpwall', lambda: [user])
    monkeypatch.setattr(helper.grp, 'getgrnam', lookup_group)
    monkeypatch.setattr(helper.subprocess, 'run', run)
    monkeypatch.setattr(helper, '_trusted_directory', lambda path: None)
    monkeypatch.setattr(policy, 'read_host_session_policy', read_policy)
    return SimpleNamespace(helper=helper, file=file, home=home, user=user,
        created=created, calls=calls)


def test_provisioning_creates_only_locked_account_home_and_disabled_policy(provisioning):
    s = provisioning
    result = s.helper.prepare()
    assert result == {'account': '3mm-terminal', 'policy_enabled': False,
        'application_started': False, 'service_started': False, 'grant_changed': False}
    assert json.loads(s.file.read_bytes()) == {'schema_version': 1, 'enabled': False}
    assert stat.S_IMODE(s.home.stat().st_mode) == 0o700
    assert stat.S_IMODE(s.file.stat().st_mode) == 0o644
    assert s.calls == [
        ['/usr/sbin/groupadd', '--system', '3mm-terminal'],
        ['/usr/sbin/useradd', '--system', '--gid', '3mm-terminal', '--home-dir', str(s.home),
            '--shell', '/usr/sbin/nologin', '--no-create-home', '--password', '!', '3mm-terminal'],
        ['/usr/bin/passwd', '-S', '3mm-terminal']]


@pytest.mark.parametrize('original', [b'{"schema_version":1,"enabled":true}\n',
    b'{"schema_version":1,"enabled":false}\n', b'{bad JSON'])
def test_provisioning_preserves_existing_policy_bytes_including_explicit_enabled_decision(provisioning, original):
    s = provisioning
    s.file.write_bytes(original)
    if original == b'{bad JSON':
        with pytest.raises(ValueError):s.helper.prepare()
    else:
        s.helper.prepare()
    assert s.file.read_bytes() == original


@pytest.mark.parametrize('fault', ['root', 'supplementary', 'home', 'shell', 'unlocked', 'uid_alias'])
def test_provisioning_refuses_unsafe_existing_account_without_changing_files(provisioning, monkeypatch, fault):
    s = provisioning
    s.created.update(user=True, group=True)
    if fault == 'root':s.user.pw_uid = 0
    if fault == 'supplementary':monkeypatch.setattr(s.helper.os, 'getgrouplist', lambda *args: [s.user.pw_gid, 0])
    if fault == 'home':s.user.pw_dir = '/root'
    if fault == 'shell':s.user.pw_shell = '/bin/bash'
    if fault == 'uid_alias':
        monkeypatch.setattr(s.helper.pwd, 'getpwall', lambda: [s.user,
            SimpleNamespace(pw_name='other', pw_uid=s.user.pw_uid)])
    if fault == 'unlocked':
        monkeypatch.setattr(s.helper.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='3mm-terminal P 01/01/2026'))
    with pytest.raises(ValueError):s.helper.prepare()
    assert not s.home.exists() and not s.file.exists()
    assert not any('useradd' in command[0] for command in s.calls)


def test_provisioning_never_overwrites_symlinked_or_malformed_policy(provisioning):
    s = provisioning
    target = s.file.with_name('unrelated.json')
    target.write_text('{"schema_version":1,"enabled":true}')
    s.file.symlink_to(target)
    with pytest.raises(ValueError):s.helper.prepare()
    assert s.file.is_symlink() and target.read_text() == '{"schema_version":1,"enabled":true}'


def test_interrupted_policy_write_leaves_no_partial_installed_policy(provisioning, monkeypatch):
    s = provisioning
    def interrupted(_):raise OSError('Simulated flush failure')
    monkeypatch.setattr(s.helper.os, 'fsync', interrupted)
    with pytest.raises(OSError, match='flush failure'):s.helper.prepare()
    assert not s.file.exists() and not list(s.file.parent.glob('.host-sessions-*'))


def test_concurrent_explicit_policy_decision_wins_without_overwrite(provisioning, monkeypatch):
    s = provisioning
    def concurrent(source, target, **kwargs):
        s.file.write_bytes(b'{"schema_version":1,"enabled":true}\n')
        raise FileExistsError(target)
    monkeypatch.setattr(s.helper.os, 'link', concurrent)
    assert s.helper.prepare()['policy_enabled']
    assert s.file.read_bytes() == b'{"schema_version":1,"enabled":true}\n'
    assert not list(s.file.parent.glob('.host-sessions-*'))
