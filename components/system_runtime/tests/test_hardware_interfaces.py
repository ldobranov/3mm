"""Isolated file/process doubles only. Never open I²C or call systemctl/reboot."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sqlite3

import pytest

from components.system_runtime import hardware_interfaces as hw

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Linux host configuration and flock')
DEVICE = 'dev_' + 'a' * 32
BOOT = b'# Owner configuration\ndtparam=audio=on\n#dtparam=i2c_arm=on\n[pi4]\ndtoverlay=vc4-kms-v3d\n'


@pytest.fixture
def host(tmp_path, monkeypatch):
    root = tmp_path/'host'
    values = {'/etc/os-release': b'ID=debian\nVERSION_CODENAME=trixie\n',
        '/boot/firmware/config.txt': BOOT,
        '/sys/firmware/devicetree/base/model': b'Raspberry Pi 3 Model B Plus Rev 1.3\0',
        '/proc/sys/kernel/random/boot_id': b'11111111-1111-4111-8111-111111111111',
        '/var/lib/3mm/agent/identity.json': json.dumps({'device_id': DEVICE}).encode()}
    for name, data in values.items():
        path = root/name.lstrip('/'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    (root/'etc/modules-load.d').mkdir()
    (root/'etc/systemd/system').mkdir(parents=True)
    database = tmp_path/'core.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE users(id INTEGER,role TEXT,is_blocked INTEGER,token_version INTEGER)')
        db.execute("INSERT INTO users VALUES(1,'admin',0,7)")
        db.execute("INSERT INTO users VALUES(2,'user',0,0)")
    monkeypatch.setattr(hw, 'i2c_group_id', lambda: 988)
    process = lambda: {'pid': 42, 'start': '1234', 'uid': 999, 'gid': 985, 'groups': [985], 'gpio_pins': []}
    return hw.HardwareInterfaces(root=root, state=root/'state', database=database,
        process=process, mutation_lock=nullcontext, enforce=False)


def request(host, identifier='b'*32):
    return {'action': 'hardware_interfaces_enable_i2c', 'device_id': DEVICE,
        'requested_by_user_id': 1, 'request_id': identifier,
        'expected_revision': host.inspect(DEVICE)['revision'], 'confirmation': 'ENABLE I2C ' + DEVICE}


def prepare(host):
    payload = request(host)
    host.queue(payload, lambda _: None)
    host.execute(payload['request_id'])
    return payload


def test_inspection_is_read_only_and_remote_selection_never_targets_core(host):
    result = host.inspect(DEVICE)
    assert result['supported'] and result['can_enable'] and not result['ready']
    assert result['pins'][0] == {'bcm': 2, 'physical': 3, 'signal': 'SDA'}
    assert not host.state.exists()
    remote = host.inspect('dev_'+'f'*32)
    assert remote['reason'] == 'remote_device_unsupported' and not remote['can_enable']
    assert host.path('/boot/firmware/config.txt').read_bytes() == BOOT


def test_enable_journals_preimages_preserves_owner_files_and_waits_for_real_boot(host):
    prepare(host)
    assert host.operation()['state'] == 'pending_reboot'
    assert bytes.fromhex(host.operation()['preimages']['/boot/firmware/config.txt']) == BOOT
    assert host.path('/boot/firmware/config.txt').read_bytes() == BOOT + hw.BOOT_BYTES
    assert host.path(hw.MODULES).read_bytes() == hw.MODULE_BYTES
    assert host.path(hw.DROPIN).read_bytes() == hw.DROPIN_BYTES
    assert b'SupplementaryGroups=i2c' in hw.DROPIN_BYTES
    assert not host.path('/etc/group').exists()  # no shared-user membership change
    pending = host.inspect(DEVICE)
    assert pending['operation']['state'] == 'pending_reboot' and not pending['ready']
    # Even a fully ready-looking Agent restart cannot prove a new kernel boot.
    host.live = lambda: {'adapter_present': True, 'device_node_present': True, 'agent_running': True,
                        'agent_access': True, 'agent_process': {'pid': 43}, 'clock_hz': 100000}
    assert host.inspect(DEVICE)['operation']['state'] == 'pending_reboot'
    assert not host.inspect(DEVICE)['ready']
    host.path('/proc/sys/kernel/random/boot_id').write_text('22222222-2222-4222-8222-222222222222')
    assert host.inspect(DEVICE)['operation']['state'] == 'verified'
    assert host.inspect(DEVICE)['ready']
    host.live = lambda: {'adapter_present': True, 'device_node_present': True, 'agent_running': True,
                        'agent_access': False, 'agent_process': {'pid': 43}, 'clock_hz': 100000}
    assert host.inspect(DEVICE)['operation']['state'] == 'verification_failed'
    assert not host.inspect(DEVICE)['ready']


def test_duplicate_and_lost_acknowledgment_do_not_schedule_or_write_again(host):
    payload, calls = request(host), []
    host.queue(payload, calls.append); host.queue(payload, calls.append)
    assert calls == [payload['request_id']]
    with pytest.raises(ValueError, match='request_id_conflict'):
        host.queue({**payload, 'confirmation': 'ENABLE I2C '+DEVICE, 'expected_revision': 'f'*64}, calls.append)
    host.execute(payload['request_id'])
    host.queue(payload, calls.append)
    with pytest.raises(ValueError, match='not_queued'):
        host.execute(payload['request_id'])
    assert calls == [payload['request_id']]


@pytest.mark.parametrize('change', ['revision', 'remote', 'confirmation', 'user', 'extra'])
def test_invalid_or_unprivileged_enable_never_mutates_files(host, change):
    payload = request(host)
    payload.update({'revision': {'expected_revision': '0'*64}, 'remote': {'device_id': 'dev_'+'f'*32,
        'confirmation': 'ENABLE I2C dev_'+'f'*32}, 'confirmation': {'confirmation': 'yes'},
        'user': {'requested_by_user_id': 2}, 'extra': {'command': 'reboot'}}[change])
    with pytest.raises(ValueError): host.queue(payload, lambda _: pytest.fail('must not schedule'))
    assert host.path('/boot/firmware/config.txt').read_bytes() == BOOT
    assert not host.path(hw.MODULES).exists()


@pytest.mark.parametrize('change', ['config', 'blocked', 'revoked', 'boot', 'pid'])
def test_admission_rechecks_authority_revision_and_host_before_first_write(host, change):
    payload = request(host); host.queue(payload, lambda _: None)
    if change == 'config': host.path('/boot/firmware/config.txt').write_bytes(BOOT+b'# owner edit\n')
    elif change in {'blocked', 'revoked'}:
        with sqlite3.connect(host.database) as db:
            db.execute('UPDATE users SET '+('is_blocked=1' if change == 'blocked' else 'token_version=8')+' WHERE id=1')
    elif change == 'boot': host.path('/proc/sys/kernel/random/boot_id').write_text('22222222-2222-4222-8222-222222222222')
    else: host.process = lambda: {'pid': 77, 'start': '999', 'uid': 999, 'gid': 985, 'groups': []}
    before = host.path('/boot/firmware/config.txt').read_bytes()
    host.execute(payload['request_id'])
    assert host.operation()['state'] == 'failed'
    assert host.path('/boot/firmware/config.txt').read_bytes() == before
    assert not host.path(hw.MODULES).exists()


@pytest.mark.parametrize('line', [b'include extra.txt', b'[pi3]\ndtparam=i2c_arm=off',
    b'dtparam=i2c_arm=off', b'dtparam=i2c_arm_baudrate=400000', b'gpio=2,3=op,dh',
    b'dtoverlay=i2c-gpio'])
def test_foreign_or_ambiguous_host_configuration_is_not_overridden(host, line):
    host.path('/boot/firmware/config.txt').write_bytes(BOOT+b'\n[all]\n'+line+b'\n')
    result = host.inspect(DEVICE)
    assert not result['supported'] and not result['can_enable']
    assert not host.state.exists()


def test_stock_multimodel_boot_config_preserves_inactive_pi5_overlay_on_pi3(host):
    # Exact active configuration supplied by the owner after the first web probe.
    boot = b'''dtparam=audio=on
camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1
dtoverlay=vc4-kms-v3d
max_framebuffers=2
disable_fw_kms_setup=1
arm_64bit=1
disable_overscan=1
arm_boost=1
[cm4]
otg_mode=1
[cm5]
dtoverlay=dwc2,dr_mode=host
[pi5]
dtoverlay=nospi10
[all]
enable_uart=1
'''
    host.path('/boot/firmware/config.txt').write_bytes(boot)
    current = host.inspect(DEVICE)
    assert current['supported'] and current['can_enable']
    assert not current['configured'] and not current['ready']
    assert not host.state.exists()  # inspection never modifies the host
    prepare(host)
    assert host.path('/boot/firmware/config.txt').read_bytes() == boot + hw.BOOT_BYTES
    assert bytes.fromhex(host.operation()['preimages']['/boot/firmware/config.txt']) == boot
    assert host.inspect(DEVICE)['operation']['state'] == 'pending_reboot'
    assert not host.inspect(DEVICE)['ready']


@pytest.mark.parametrize('section', ['all', 'pi3', 'pi3+'])
def test_unknown_overlay_in_an_applicable_model_filter_remains_blocked(host, section):
    host.path('/boot/firmware/config.txt').write_bytes(
        f'[all]\ndtparam=audio=on\n[{section}]\ndtoverlay=nospi10\n'.encode())
    assert host.inspect(DEVICE)['reason'] == 'unverified_overlay_conflict'
    assert not host.inspect(DEVICE)['can_enable']


@pytest.mark.parametrize('body', [b'[pi5]\ndtoverlay=nospi10', b'[cm4]\ndtoverlay=unknown',
    b'[cm5]\ndtparam=i2c_arm=off', b'[pi4]\ndtparam=i2c_arm=on', b'[pi4]\ngpio=2,3=op,dh'])
def test_provably_foreign_model_settings_do_not_block_the_local_profile(host, body):
    host.path('/boot/firmware/config.txt').write_bytes(b'[all]\ndtparam=audio=on\n'+body+b'\n[all]\n')
    assert host.inspect(DEVICE)['can_enable']


@pytest.mark.parametrize('body', [b'[pi5]\n[pi3]\ndtoverlay=nospi10',
    b'[cm5]\n[pi3+]\ngpio=2=op,dh', b'[pi5]\n[all]\ndtparam=i2c_arm=off'])
def test_new_model_filter_and_all_reset_cannot_hide_active_conflicts(host, body):
    host.path('/boot/firmware/config.txt').write_bytes(body+b'\n')
    assert not host.inspect(DEVICE)['supported']


@pytest.mark.parametrize('body', [b'[EDID=example]\ndtoverlay=nospi10',
    b'[gpio4=1]\n[pi3]\ndtparam=i2c_arm=on', b'[tryboot]\n[pi3+]\ndtparam=i2c_arm=on',
    b'[future-model]\n[pi3]\ndtoverlay=vc4-kms-v3d', b'[pi5\ndtoverlay=nospi10',
    b'[PI5]\ndtoverlay=nospi10', b'[pi5]\n[ALL]\ndtoverlay=nospi10'])
def test_unknown_or_malformed_conditions_remain_unverified_until_all(host, body):
    host.path('/boot/firmware/config.txt').write_bytes(body+b'\n')
    assert host.inspect(DEVICE)['reason'] == 'unverified_boot_filter'
    assert not host.inspect(DEVICE)['can_enable']


def test_all_clears_unknown_filter_but_model_filter_alone_does_not(host):
    host.path('/boot/firmware/config.txt').write_bytes(
        b'[EDID=example]\nhdmi_drive=2\n[all]\ndtparam=audio=on\n')
    assert host.inspect(DEVICE)['can_enable']


@pytest.mark.parametrize('section', ['pi3', 'pi3+'])
def test_matching_model_i2c_settings_are_read_without_modifying_them(host, section):
    boot = f'[{section}]\ndtparam=i2c_arm=on,i2c_arm_baudrate=100000\n'.encode()
    host.path('/boot/firmware/config.txt').write_bytes(boot)
    assert host.inspect(DEVICE)['can_enable']
    prepare(host)
    assert host.path('/boot/firmware/config.txt').read_bytes() == boot
    assert host.inspect(DEVICE)['operation']['state'] == 'pending_reboot'


@pytest.mark.parametrize('model,matching,foreign', [
    ('Raspberry Pi Zero W Rev 1.1', 'pi0w', 'pi02'),
    ('Raspberry Pi Zero W Rev 1.1', 'pi0', 'cm0'),
    ('Raspberry Pi 3 Model B Plus Rev 1.4', 'pi3+', 'cm3+'),
    ('Raspberry Pi 4 Model B Rev 1.5', 'pi4', 'cm4'),
    ('Raspberry Pi 5 Model B Rev 1.0', 'pi5', 'cm5'),
])
def test_supported_board_uses_its_firmware_model_filters_not_compute_module_aliases(host, model, matching, foreign):
    host.path('/sys/firmware/devicetree/base/model').write_bytes(model.encode()+b'\0')
    host.path('/boot/firmware/config.txt').write_bytes(f'[{foreign}]\ndtoverlay=unknown\n[all]\n'.encode())
    assert host.inspect(DEVICE)['can_enable']
    host.path('/boot/firmware/config.txt').write_bytes(f'[{matching}]\ndtoverlay=unknown\n'.encode())
    assert host.inspect(DEVICE)['reason'] == 'unverified_overlay_conflict'


def test_include_is_still_refused_in_a_foreign_model_section(host):
    host.path('/boot/firmware/config.txt').write_bytes(b'[pi5]\ninclude extra.txt\n[all]\n')
    assert host.inspect(DEVICE)['reason'] == 'host_configuration_conflict'


def test_managed_path_symlink_foreign_contents_and_inactive_agent_are_fenced(host):
    link = host.path('/etc/modules-load.d'); link.rmdir(); link.symlink_to(host.root/'etc')
    assert host.inspect(DEVICE)['reason'] == 'unsafe_managed_path'
    link.unlink(); link.mkdir()
    host.path(hw.MODULES).write_bytes(b'owner config\n')
    assert host.inspect(DEVICE)['reason'] == 'managed_file_conflict'
    host.path(hw.MODULES).unlink(); host.process = lambda: None
    assert not host.inspect(DEVICE)['can_enable']


def test_write_failure_restores_preimages_without_overwriting_a_new_owner_edit(host):
    payload = request(host); host.queue(payload, lambda _: None)
    original = host.replace
    def fail(name, before, after):
        if name == hw.MODULES: raise PermissionError('read-only modules path')
        original(name, before, after)
    host.replace = fail
    host.execute(payload['request_id'])
    assert host.operation()['state'] == 'failed'
    assert host.path('/boot/firmware/config.txt').read_bytes() == BOOT


def test_rollback_does_not_clobber_a_concurrent_owner_edit(host):
    payload = request(host); host.queue(payload, lambda _: None)
    original = host.replace
    def fail(name, before, after):
        if name == hw.MODULES:
            host.path('/boot/firmware/config.txt').write_bytes(BOOT+b'# new owner edit\n')
            raise PermissionError('failure after external edit')
        original(name, before, after)
    host.replace = fail
    host.execute(payload['request_id'])
    assert host.operation()['state'] == 'recovery_required'
    assert host.path('/boot/firmware/config.txt').read_bytes() == BOOT+b'# new owner edit\n'


def test_hard_interruption_retains_preimages_and_never_auto_resumes_partial_writes(host):
    payload = request(host); host.queue(payload, lambda _: None)
    original = host.replace
    def power_loss(name, before, after):
        if name == hw.MODULES: raise KeyboardInterrupt('simulated worker loss')
        original(name, before, after)
    host.replace = power_loss
    with pytest.raises(KeyboardInterrupt): host.execute(payload['request_id'])
    assert host.operation()['state'] == 'applying'
    assert host.operation()['preimages']['/boot/firmware/config.txt'] == BOOT.hex()
    host.worker_active = lambda _: False
    assert host.inspect(DEVICE)['operation']['state'] == 'recovery_required'
    assert not host.inspect(DEVICE)['ready']
    assert not host.path(hw.MODULES).exists()


def test_lost_scheduler_reply_after_completion_does_not_clobber_pending_result(host):
    payload = request(host)
    def completed_but_lost(identifier):
        host.execute(identifier)
        raise TimeoutError('lost scheduling response')
    with pytest.raises(TimeoutError): host.queue(payload, completed_but_lost)
    assert host.inspect(DEVICE)['operation']['state'] == 'pending_reboot'


def test_interrupted_worker_is_not_replayed_by_status_or_a_new_request(host):
    payload = request(host); host.queue(payload, lambda _: None)
    host.worker_active = lambda _: False
    status = host.inspect(DEVICE)
    assert status['operation']['state'] == 'recovery_required' and not status['can_enable']
    with pytest.raises(ValueError): host.queue(request(host, 'c'*32), lambda _: pytest.fail('no replay'))
    assert host.path('/boot/firmware/config.txt').read_bytes() == BOOT


def test_ambiguous_schedule_remains_fenced_and_no_automatic_retry(host):
    payload = request(host)
    with pytest.raises(TimeoutError):
        host.queue(payload, lambda _: (_ for _ in ()).throw(TimeoutError()))
    assert host.inspect(DEVICE)['operation']['state'] == 'recovery_required'
    assert not host.inspect(DEVICE)['can_enable']


def test_restart_requires_separate_exact_device_review_and_is_not_repeated(host):
    payload = prepare(host)
    current = host.inspect(DEVICE)
    reboot = {'action': 'hardware_interfaces_restart', 'device_id': DEVICE, 'requested_by_user_id': 1,
        'request_id': 'c'*32, 'source_request_id': payload['request_id'],
        'expected_revision': current['revision'], 'confirmation': 'RESTART '+DEVICE}
    calls = []
    with pytest.raises(ValueError): host.restart({**reboot, 'confirmation': 'RESTART'}, calls.append)
    assert calls == []
    host.restart(reboot, calls.append); host.restart(reboot, calls.append)
    assert calls == ['restart_device']
    assert host.inspect(DEVICE)['operation']['restart_request_id'] == reboot['request_id']
    with pytest.raises(ValueError): host.restart({**reboot, 'request_id': 'd'*32}, calls.append)
    assert calls == ['restart_device']


def test_changed_configuration_after_apply_never_becomes_ready(host):
    prepare(host)
    host.path(hw.DROPIN).write_bytes(b'# changed\n')
    assert host.inspect(DEVICE)['operation']['state'] == 'recovery_required'
    assert not host.inspect(DEVICE)['ready']


@pytest.fixture
def live_i2c(host, monkeypatch):
    """Kernel metadata doubles matching the observed Pi sysfs links, no bus I/O."""
    import stat
    from types import SimpleNamespace
    adapter = host.path('/sys/bus/i2c/devices/i2c-1')
    controller = host.path('/sys/devices/platform/soc/3f804000.i2c/i2c-1')
    of_node = host.path('/sys/firmware/devicetree/base/soc/i2c@7e804000')
    adapter.parent.mkdir(parents=True); controller.mkdir(parents=True); of_node.mkdir(parents=True)
    adapter.symlink_to(os.path.relpath(controller, adapter.parent), target_is_directory=True)
    (controller/'of_node').symlink_to(os.path.relpath(of_node, controller), target_is_directory=True)
    clock = of_node/'clock-frequency'
    clock.write_bytes(b'\x00\x01\x86\xa0')
    node, service_node = host.path('/dev/i2c-1'), host.path('/proc/42/root/dev/i2c-1')
    real_lstat, real_stat = Path.lstat, Path.stat
    fake = SimpleNamespace(st_mode=stat.S_IFCHR | 0o660, st_rdev=os.makedev(89, 1), st_uid=0, st_gid=988)
    monkeypatch.setattr(Path, 'lstat', lambda p: fake if p == node else real_lstat(p))
    monkeypatch.setattr(Path, 'stat', lambda p, **kw: fake if p == service_node else real_stat(p, **kw))
    monkeypatch.setattr(os, 'listxattr', lambda _: [])
    host.process = lambda: {'pid': 42, 'start': '1', 'uid': 999, 'gid': 985, 'groups': [988]}
    assert not host.path('/sys/class/i2c-adapter').exists()
    return clock


def test_running_agent_mode_permissions_clock_and_acl_not_helper_root_prove_access(host, monkeypatch, live_i2c):
    host.process = lambda: {'pid': 42, 'start': '1', 'uid': 999, 'gid': 985, 'groups': [985]}
    assert not host.live()['agent_access']  # configured group not in running Agent
    host.process = lambda: {'pid': 42, 'start': '1', 'uid': 999, 'gid': 985, 'groups': [988]}
    live = host.live()
    assert live['agent_access'] and live['adapter_present'] and live['clock_hz'] == 100000
    monkeypatch.setattr(os, 'listxattr', lambda _: ['system.posix_acl_access'])
    assert not host.live()['agent_access']  # unknown ACL is not a readiness proof


def test_post_reboot_bus_sysfs_verification_preserves_request_and_configuration(host, live_i2c):
    payload = prepare(host)
    pending = host.inspect(DEVICE)
    assert pending['operation']['state'] == 'pending_reboot' and not pending['ready']
    calls = []
    host.restart({'action': 'hardware_interfaces_restart', 'device_id': DEVICE,
        'requested_by_user_id': 1, 'request_id': 'c'*32, 'source_request_id': payload['request_id'],
        'expected_revision': pending['revision'], 'confirmation': 'RESTART '+DEVICE}, calls.append)
    files = [host.state/'operation.json', host.path('/boot/firmware/config.txt'),
             host.path(hw.MODULES), host.path(hw.DROPIN)]
    before = [path.read_bytes() for path in files]
    host.path('/proc/sys/kernel/random/boot_id').write_text('22222222-2222-4222-8222-222222222222')
    for _ in range(2):
        status = host.inspect(DEVICE)
        assert status['ready'] and status['operation']['state'] == 'verified'
        assert status['operation']['request_id'] == payload['request_id']
        assert status['operation']['restart_request_id'] == 'c'*32
        assert status['live']['adapter_present'] and status['live']['clock_hz'] == 100000
    assert [path.read_bytes() for path in files] == before
    assert calls == ['restart_device']  # status never reschedules activation or reboot


@pytest.mark.parametrize('clock', [None, b'\x00\x01\x86', (400000).to_bytes(4, 'big')])
def test_bus_sysfs_without_verified_100khz_cannot_confirm_reboot(host, live_i2c, clock):
    prepare(host)
    journal = (host.state/'operation.json').read_bytes()
    if clock is None:
        live_i2c.unlink()
    else:
        live_i2c.write_bytes(clock)
    host.path('/proc/sys/kernel/random/boot_id').write_text('22222222-2222-4222-8222-222222222222')
    status = host.inspect(DEVICE)
    assert status['live']['adapter_present'] and status['live']['agent_access']
    assert status['reason'] == 'live_i2c_speed_unverified_or_conflicting'
    assert not status['ready'] and not status['can_enable']
    assert (host.state/'operation.json').read_bytes() == journal


@pytest.mark.parametrize('peer', [None, True, 998])
def test_helper_rejects_foreign_or_claimed_core_peer_before_hardware_io(host, monkeypatch, peer):
    from components.system_runtime import update_helper
    monkeypatch.setattr(update_helper, '_service_ids', lambda *_: (999, 985))
    response = update_helper._handle_request({'action': 'hardware_interfaces_status',
        'device_id': DEVICE, 'requested_by_user_id': 1}, stage_root=host.root/'stage',
        state_root=host.root/'helper', allowlist=host.root/'allow', status_file=host.root/'status',
        application_database=host.database, relational_peer_uid=peer)
    assert response == {'ok': False, 'error': 'hardware_interfaces_unavailable'}
    assert not host.state.exists()


def test_fixed_worker_has_no_shell_bus_io_or_restart_and_preserves_main_helper_hardening():
    from components.system_runtime.update_helper import UpdateMutationBoundary
    calls = []
    class Runner:
        def run(self, command): calls.append(command); return 0
    boundary = UpdateMutationBoundary(runner=Runner())
    boundary.schedule_hardware_interfaces('a'*32)
    assert len(calls) == 1
    assert calls[0][-4:] == ['-m', 'components.system_runtime.hardware_interfaces', '--request-id', 'a'*32]
    assert not any(x in calls[0] for x in ('reboot', 'modprobe', 'raspi-config', 'sh', '/bin/sh'))
    assert '--property=ProtectSystem=strict' in calls[0]
    with pytest.raises(ValueError): boundary.schedule_hardware_interfaces('../../bad')
    unit = (Path(__file__).parents[3]/'deployment/systemd/3mm-update-helper.service').read_text()
    assert '3mm-hardware-interfaces' in unit
    assert '/boot' not in unit  # writable boot mount exists only in the fixed worker


def test_release_requires_the_hardware_api_and_fixed_worker_before_activation():
    from deployment.deployment_contract import validate_deployment_contract, DeploymentContractError
    root = Path(__file__).parents[3]
    raw = (root/'deployment/deployment-contract.json').read_bytes()
    required = set(json.loads(raw)['required_files'])
    # A malformed baseline (including an unsorted required_files list) must not
    # make every missing-file assertion pass for the wrong reason.
    assert validate_deployment_contract(raw, required).schema_version == 2
    for name in ('backend/devices/__init__.py', 'backend/devices/hardware_interfaces.py',
                 'components/system_runtime/hardware_interfaces.py'):
        assert name in required and (root/name).is_file()
        with pytest.raises(DeploymentContractError, match='incomplete'):
            validate_deployment_contract(raw, required-{name})


def test_observed_socket_peer_not_payload_claim_authorizes_hardware_inspection(host, monkeypatch):
    import socket
    from components.system_runtime import update_helper
    monkeypatch.setattr(update_helper, '_service_ids', lambda *_: (os.getuid(), os.getgid()))
    class Workflow:
        def __init__(self, **kwargs): pass
        def inspect(self, device): return {'device_id': device, 'supported': False}
    monkeypatch.setattr(hw, 'HardwareInterfaces', Workflow)
    client, server = socket.socketpair()
    with client, server:
        client.sendall(json.dumps({'action': 'hardware_interfaces_status', 'device_id': DEVICE,
                                  'requested_by_user_id': 1}).encode()+b'\n')
        update_helper._serve_connection(server, stage_root=host.root/'stage', state_root=host.root/'helper',
            allowlist=host.root/'allow', status_file=host.root/'status', application_database=host.database)
        assert json.loads(client.recv(4096))['interfaces']['device_id'] == DEVICE


def test_worker_can_start_synchronously_without_racing_the_admission_lock(host):
    payload = request(host)
    host.queue(payload, host.execute)
    assert host.operation()['state'] == 'pending_reboot'
