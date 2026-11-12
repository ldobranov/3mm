"""Actual seals/registry/authority for the local host-account session profile.

Root policy and sockets are doubled; no installed user, shell or device is used.
Real Linux/systemd PTY acceptance remains a separate disposable-host gate.
"""
import io
import json
import zipfile
from dataclasses import replace

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.applications.sessions import local
from backend.db.device import Device
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.artifacts.packages import validate_module_package
from backend.devices.capabilities.registry import registered_capabilities
from backend.tests.test_application_local_sessions import (
    local_app, session_app, checkpoint_app, managed_installed, source_installed,
    source_subject, native, decide, review, identity,
)
from components.system_runtime.host_session_policy import HostSessionPolicy
from components.system_runtime.session_worker_client import HostAccountSessionProvider


@pytest.fixture
def host_app(local_app, monkeypatch):
    s = local_app
    definition = s.validated.application_extension.model_dump(mode='json')
    definition['session_providers'][0]['resource_profile'] = 'host_account_session_v1'
    payload = io.BytesIO()
    with zipfile.ZipFile(s.archive) as original, zipfile.ZipFile(payload, 'w') as archive:
        for name in original.namelist():
            archive.writestr(name, json.dumps(definition).encode() if name == 'application-extension.json' else original.read(name))
    s.validated = validate_module_package(payload.getvalue())
    s.archive = s.root/'modules'/(s.validated.sha256+'.zip')
    s.archive.write_bytes(payload.getvalue())
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(
            sha256=s.validated.sha256, file_path=str(s.archive), size_bytes=len(payload.getvalue())))
    s.host_policy = HostSessionPolicy(True, 'e'*64, '3mm-terminal', 997, 996,
        '/var/lib/3mm-terminal', '/usr/sbin/nologin', (996,))
    monkeypatch.setattr(local, 'read_host_session_policy', lambda: s.host_policy)
    monkeypatch.setattr(local, 'host_supervisor_available', lambda: True)
    monkeypatch.setattr(local, 'host_supervisor_generation', lambda: (4, 5, 6))
    s.manager._prepare(1)
    return s


def admit(s):
    proof = native(s)
    decide(s, decide(s, review(s, proof), 'approve'), 'apply')
    with s.engine.begin() as db:
        db.execute(update(Installation).where(Installation.id == 1).values(
            enabled=True, status='active', authority_epoch=identity()))
    decide(s, decide(s, review(s, proof), 'approve'), 'apply')
    return s.session_authority._resolve(1, 'console', 'ses_'+'c'*32,
        'Bearer '+s.user_token, s.request)


def test_host_profile_and_exact_account_are_reviewed_before_any_execution(host_app):
    s = host_app
    with Session(s.engine) as db:
        row = registered_capabilities(db, db.get(Device, 1))[0]
        account = json.loads(row['metadata']['host_account'])
        assert row['metadata']['resource_profile'] == account['resource_profile'] == 'host_account_session_v1'
        assert account['account'] == '3mm-terminal' and account['uid'] == 997
    binding, resource = admit(s)
    assert resource.host_account.policy_sha256 == s.host_policy.sha256
    runtime = local.runtime_for_resource(s.engine, resource.model_dump(mode='json'))
    assert isinstance(runtime.provider, HostAccountSessionProvider)
    assert runtime.provider.session_id is None  # Discovery/review did not launch.
    assert runtime.is_current()
    # The grant, not just a current socket, pins the exact root policy episode.
    s.host_policy = replace(s.host_policy, sha256='f'*64)
    assert not runtime.is_current()
    assert local.runtime_for_resource(s.engine, resource.model_dump(mode='json')) is None
    with pytest.raises(ValueError):
        s.session_authority.check(binding, authorization='Bearer '+s.user_token,
            request=s.request, session_id=binding.session_id, operation='status')
    assert not s.manager.inspect(1)['grant_effective']


@pytest.mark.parametrize('fault', ['disabled_policy', 'missing_policy', 'supervisor', 'foreign_device', 'foreign_provider', 'wrong_policy', 'missing_host_identity'])
def test_host_profile_has_no_isolated_or_remote_fallback(host_app, monkeypatch, fault):
    s = host_app
    _binding, resource = admit(s)
    value = resource.model_dump(mode='json')
    if fault in {'disabled_policy', 'missing_policy'}:
        def refuse():
            raise ValueError('Host-account sessions are disabled or untrusted')
        monkeypatch.setattr(local, 'read_host_session_policy', refuse)
    elif fault == 'supervisor': monkeypatch.setattr(local, 'host_supervisor_available', lambda: False)
    elif fault == 'foreign_device': value['target_device_id'] = 'dev_'+'f'*32
    elif fault == 'foreign_provider': value['declaration']['provider_id'] = 'org.other.provider'
    elif fault == 'wrong_policy': value['host_account']['policy_sha256'] = 'f'*64
    else: value.pop('host_account')
    assert local.runtime_for_resource(s.engine, value) is None


def test_host_grant_rechecks_application_revocation(host_app):
    s = host_app
    binding, resource = admit(s)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(),
        expected_revision=s.manager.inspect(1)['grant_record_revision'])
    with pytest.raises(ValueError):
        s.session_authority.check(binding, authorization='Bearer '+s.user_token,
            request=s.request, session_id=binding.session_id, operation='input')


def test_isolated_resource_serialization_does_not_acquire_host_access(local_app):
    s = local_app
    _binding, resource = admit(s)
    assert resource.host_account is None
    assert 'host_account' not in resource.model_dump(mode='json')
    runtime = local.runtime_for_resource(s.engine, resource.model_dump(mode='json'))
    assert runtime is not None and not isinstance(runtime.provider, HostAccountSessionProvider)
