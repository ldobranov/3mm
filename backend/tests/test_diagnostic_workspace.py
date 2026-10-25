import json
import pytest
from backend.tests.test_diagnostics import _client, use_test_jwt_secret
from three_mm_protocol.diagnostics import DiagnosticSession
from backend.services import diagnostic_workspace as workspace


@pytest.fixture
def environment(monkeypatch):
    client,db,admin,viewer=_client();session=DiagnosticSession('core','1.0')
    monkeypatch.setattr('backend.routes.diagnostics.core_diagnostics',session)
    yield client,db,{'Authorization':'Bearer '+admin},{'Authorization':'Bearer '+viewer},session
    db.close()


def test_workspace_and_merge_require_current_admin_and_scope_is_closed(environment,monkeypatch):
    client,db,admin,viewer,session=environment;seen=[]
    monkeypatch.setattr('backend.routes.diagnostics.observe',lambda *a:seen.append(True) or {'components':[]})
    for method,path in [('GET','/workspace'),('GET','/timeline'),('POST','/timeline/merge')]:
        assert client.request(method,'/api/v1/diagnostics'+path).status_code==401
        assert client.request(method,'/api/v1/diagnostics'+path,headers=viewer).status_code==403
    assert not seen
    assert client.get('/api/v1/diagnostics/workspace',headers=admin).status_code==200
    assert seen==[True]
    for bad in [{'operation':'password=secret'},{'instance_id':'foreign'},{'profile':'root'},{'trace_id':'arbitrary'},{'ttl_seconds':True}]:
        assert client.post('/api/v1/diagnostics/session',headers=admin,json=bad).status_code==422
    response=client.post('/api/v1/diagnostics/session',headers=admin,json={'profile':'development','operation':'checkpoint.get','instance_id':'a'*24})
    assert response.status_code==200 and response.json()['scope']['profile']=='development'
    assert not db.new and not db.dirty and not db.deleted
    assert client.delete('/api/v1/diagnostics/session',headers=admin).json()['active'] is False


def test_merge_rejects_secret_labels_and_never_stores_imported_state(environment):
    client,db,admin,viewer,session=environment
    sdk=DiagnosticSession('sdk','1.3');sdk.start();sdk.record(trace_id='platform_'+'a'*32,stage='sdk.call',operation='checkpoint.get',instance_id='b'*24,result='denied',reason='operation_denied',duration_ms=1)
    with sdk.export() as chunks:body=b''.join(chunks)
    response=client.post('/api/v1/diagnostics/timeline/merge',headers=admin,content=body)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert response.json()['records'][0]['source']=='imported'
    assert client.get('/api/v1/diagnostics/timeline',headers=admin).json()['records']==[]
    assert client.post('/api/v1/diagnostics/timeline/merge',headers=admin,content=body.replace(b'operation_denied',b'password=secret')).status_code==422
    assert client.post('/api/v1/diagnostics/timeline/merge',headers=admin,content=b'x'*(4*1024*1024+1)).status_code==413
    # A previously accepted diagnostic request does not preserve a revoked login.
    from backend.db.user import User
    user=db.get(User,1);user.token_version+=1;db.commit()
    assert client.get('/api/v1/diagnostics/timeline',headers=admin).status_code==401


def test_busy_or_failed_collector_returns_explicit_unknown_without_waiting(monkeypatch):
    from backend.config import AppSettings
    monkeypatch.setattr(workspace,'component_inventory',lambda:[{'component':'agent','build_id':None,'health':'unknown','reason':'metadata_unavailable'}])
    with workspace._PROBE:
        assert workspace.observe(AppSettings(),{})['probe_status']=='busy'
    monkeypatch.setattr(workspace,'_http_identity',lambda *a,**k:(_ for _ in ()).throw(OSError('password=secret')))
    result=workspace.observe(AppSettings(),{})
    assert next(row for row in result['components'] if row['component']=='agent')['health']=='unavailable' and 'secret' not in json.dumps(result)


def test_collector_import_slot_refuses_instead_of_queuing_core_work(environment):
    from backend.routes.diagnostics import _merge_lock
    client,db,admin,viewer,session=environment
    with _merge_lock:
        assert client.post('/api/v1/diagnostics/timeline/merge',headers=admin,content=b'{}').status_code==409
    assert client.get('/api/v1/diagnostics/session',headers=admin).status_code==200


def test_busy_observer_does_not_read_any_component_files(monkeypatch):
    from backend.config import AppSettings
    def unexpected():raise AssertionError('Busy collector read component metadata')
    monkeypatch.setattr(workspace,'component_inventory',unexpected)
    with workspace._PROBE:
        result=workspace.observe(AppSettings(),{})
    assert result['probe_status']=='busy' and all(row['health']=='unknown' for row in result['components'][1:])
