"""Actual grant, sealed receipts, signed POSIX worker and streaming SDK."""
import base64
import hashlib
import os
import uuid

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_files as service
from backend.tests.test_application_file_execution import (
    file_app, managed_installed, source_subject, source_installed, native, decide,
    identity, execute, revoke, status,
)
from three_mm_runtime.application_file_executor import ApplicationFileExecutor
from three_mm_application_sdk.tests.test_media import request

pytestmark = [pytest.mark.skipif(os.name != 'posix', reason='Actual POSIX authority and worker'),
    pytest.mark.parametrize('file_app', [dict(file_contract_version=2, max_file_bytes=2*1024*1024,
        max_total_bytes=4*1024*1024, max_files=10, max_uploads=2, max_staging_bytes=4*1024*1024,
        upload_ttl_seconds=60, public_links=True, media_transforms=True)], indirect=True)]


def grant(s):
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=False, status='disabled'))
    n = native(s)
    def apply():
        plan = s.manager.create_review(1, actor_token=s.token, request_id=identity(), native_review_id=n['native_review_id'], scopes=s.manager.inspect(1)['scopes'])
        assert {r['operation'] for r in plan['resources']['private_files']} == {'read','write','publish','transform'}
        decide(s, decide(s, plan, 'approve'), 'apply')
    apply()
    with s.engine.begin() as db:
        db.execute(update(Installation).values(enabled=True, status='active', authority_epoch=identity()))
    apply()


def result(s, op, **fields):
    value = execute(s, request(op, **fields))
    assert value['receipt']['outcome'] == 'completed', value
    return value.get('file_result', value['receipt'].get('result'))


def test_actual_stream_receipts_link_revoke_and_no_redispatch(file_app):
    s = file_app
    grant(s)
    content = b'bounded stream'*100000
    digest = hashlib.sha256(content).hexdigest()
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        start = request('begin', file_id='document', size_bytes=len(content), sha256=digest, filename='document.bin', content_type='application/octet-stream', expected_sha256=None)
        first = execute(s, start)
        assert first['receipt']['outcome'] == 'completed', first
        upload_id = first['file_result']['upload_id']
        assert execute(s, start)['historical']
        for offset in range(0, len(content), 256*1024):
            assert result(s, 'append', upload_id=upload_id, offset=offset, content_base64=base64.b64encode(content[offset:offset+256*1024]).decode())['ok']
        final = request('finalize', upload_id=upload_id)
        finished = execute(s, final)
        assert finished['receipt']['outcome'] == 'completed'
        assert finished['file_result']['file']['sha256'] == digest
        link = result(s, 'link', file_id='document', sha256=digest, token='b'*64, ttl_seconds=60, max_downloads=2)
        assert result(s, 'public_stat', link_id=link['link_id'], token='b'*64)['ok']
        revoke(s)
        assert execute(s, final)['historical']
        with pytest.raises(service.ApplicationFileAuthorityError):
            result(s, 'public_stat', link_id=link['link_id'], token='b'*64)
        with pytest.raises(service.ApplicationFileAuthorityError):
            result(s, 'read', file_id='document', sha256=digest, offset=0, length=10)
    assert not (s.runtime/'data/sdk-files').exists()


def test_lost_finalize_ack_is_status_only_and_keeps_committed_data(file_app, monkeypatch):
    s = file_app
    grant(s)
    with ApplicationFileExecutor(s.runtime, s.metadata, s.secret):
        upload = result(s, 'begin', file_id='empty', size_bytes=0, sha256=hashlib.sha256(b'').hexdigest(), filename='empty', content_type='text/plain', expected_sha256=None)
        original = service.call_file_executor
        calls = []
        def lost(path, secret, action, payload, **kwargs):
            value = original(path, secret, action, payload, **kwargs)
            if action == 'execute' and payload['request']['operation'] == 'finalize':
                calls.append(payload)
                raise OSError('lost acknowledgement')
            return value
        monkeypatch.setattr(service, 'call_file_executor', lost)
        intent = request('finalize', upload_id=upload['upload_id'])
        assert execute(s, intent)['receipt']['outcome'] == 'execution_unconfirmed'
        assert execute(s, intent)['historical']
        assert len(calls) == 1
        assert result(s, 'stat', file_id='empty')['file']['size_bytes'] == 0
        assert status(s, intent['request_id'])['receipt']['outcome'] == 'execution_unconfirmed'


def test_public_python_sdk_uses_signed_gateway_and_host_selected_profile(file_app,monkeypatch):
    import backend.database
    from backend.services.application_platform import ApplicationPlatformServer
    from three_mm_platform_wire import COMPATIBILITY_ACTIONS
    from three_mm_application_sdk import ApplicationPlatformClient, ApplicationScopedMediaStorage, ApplicationFileStorageError
    from three_mm_runtime.application_host import _private_file_adapter
    s=file_app;grant(s)
    monkeypatch.setattr(backend.database,'SessionLocal',lambda:Session(s.engine))
    keys=s.runtime.parent/'keys';keys.mkdir()
    (keys/(s.metadata['instance_id']+'.key')).write_bytes(s.secret)
    gateway=ApplicationPlatformServer(s.runtime.parent/'platform.sock',keys,allowed_actions=COMPATIBILITY_ACTIONS)
    gateway.start()
    files=_private_file_adapter(s.metadata['storage'],s.runtime/'data',ApplicationPlatformClient(gateway.socket_path,s.metadata['instance_id'],s.secret))
    assert isinstance(files,ApplicationScopedMediaStorage) and files.limits.max_file_bytes==2*1024*1024
    data=b'signed bounded chunks'*60000;digest=hashlib.sha256(data).hexdigest()
    try:
        with ApplicationFileExecutor(s.runtime,s.metadata,s.secret):
            started=files.begin('sample',len(data),digest,filename='data.bin',content_type='application/octet-stream')
            for offset in range(0,len(data),256*1024):files.append(started['upload_id'],offset,data[offset:offset+256*1024])
            assert files.upload_status(started['upload_id'])['upload']['offset']==len(data)
            intent=identity();files.finalize(started['upload_id'],request_id=intent)
            assert b''.join(files.iter_read('sample',digest))==data
            assert files.operation_status(intent)['receipt']['outcome']=='completed'
            assert files.list_files()['items'][0]['sha256']==digest
            revoke(s)
            with pytest.raises(ApplicationFileStorageError):files.stat('sample')
    finally:gateway.stop()
