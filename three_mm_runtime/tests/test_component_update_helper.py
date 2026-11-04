import json
import os
import socket
import pytest
from three_mm_runtime import update_helper, component_updates, hardware_interfaces
from three_mm_runtime.update_helper import UpdateMutationBoundary
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError, ComponentUpdateNotAccepted


@pytest.mark.parametrize('peer',[None,True,999])
def test_component_helper_refuses_unobserved_or_foreign_core_peer(tmp_path,monkeypatch,peer):
    monkeypatch.setattr(update_helper,'_service_ids',lambda *a:(1000,1000))
    result=update_helper._handle_request(dict(action='component_status',component='agent',target_id='local',requested_by_user_id=1),
        stage_root=tmp_path/'stage',state_root=tmp_path/'state',allowlist=tmp_path/'allow',status_file=tmp_path/'status',relational_peer_uid=peer)
    assert result=={'ok':False,'error':'component_update_unavailable'}


@pytest.mark.skipif(os.name!='posix',reason='Real kernel Unix peer credentials')
def test_real_kernel_peer_and_committed_admin_are_required(tmp_path,monkeypatch):
    calls=[]
    class Workflow:
        def __init__(self,**kw): pass
        def status(self,c,t): calls.append((c,t)); return {'ready':True}
    monkeypatch.setattr(update_helper,'_service_ids',lambda *a:(os.getuid(),os.getgid()))
    monkeypatch.setattr(component_updates,'ComponentUpdates',Workflow)
    monkeypatch.setattr(hardware_interfaces,'admin_revision',lambda db,u: calls.append(u) or 1)
    client,server=socket.socketpair()
    with client,server:
        client.sendall(json.dumps(dict(action='component_status',component='agent',target_id='local',requested_by_user_id=7)).encode()+b'\n')
        update_helper._serve_connection(server,stage_root=tmp_path/'stage',state_root=tmp_path/'state',allowlist=tmp_path/'allow',status_file=tmp_path/'status')
        assert json.loads(client.recv(4096))['component']['ready'] is True
    assert calls==[7,('agent','local')]


def test_scheduler_is_a_fixed_bounded_worker_not_a_user_program():
    calls=[]
    class Runner:
        def run(self,args): calls.append(args); return 0
    boundary=UpdateMutationBoundary(runner=Runner())
    boundary.schedule_component_update('a'*32)
    assert len(calls)==1 and calls[0][-3:]==['three_mm_runtime.component_updates','--job-id','a'*32]
    assert '--property=RuntimeMaxSec=300s' in calls[0]
    assert '-B' in calls[0]
    assert not any(v.startswith('--artifact') or v.startswith('--url') for v in calls[0])
    with pytest.raises(ValueError):boundary.schedule_component_update('../../bad')


def test_client_checks_ack_identity_without_repeating_request(monkeypatch):
    calls=[]
    def reply(self,payload,**kw):calls.append(payload);return {'request_id':'f'*32}
    monkeypatch.setattr(UpdateHelperClient,'_request',reply)
    client=UpdateHelperClient('/unused')
    payload=dict(action='component_prepare',component='agent',target_id='local',requested_by_user_id=1,request_id='a'*32,expected_operation_id=None)
    with pytest.raises(UpdateHelperError):client.component_operation(payload)
    assert calls==[payload]


def test_root_preflight_refusal_and_client_negative_ack_remain_distinct(tmp_path,monkeypatch):
    class Workflow:
        def __init__(self,**kw):pass
        def queue(self,*a):raise component_updates.ComponentNotAccepted('private reason')
    monkeypatch.setattr(component_updates,'ComponentUpdates',Workflow)
    monkeypatch.setattr(update_helper,'_service_ids',lambda *a:(1000,1000))
    monkeypatch.setattr(hardware_interfaces,'admin_revision',lambda *a:1)
    payload=dict(action='component_prepare',component='agent',target_id='local',requested_by_user_id=1,request_id='a'*32,expected_operation_id=None)
    result=update_helper._handle_request(payload,stage_root=tmp_path/'stage',state_root=tmp_path/'state',allowlist=tmp_path/'allow',status_file=tmp_path/'status',relational_peer_uid=1000)
    assert result=={'ok':False,'error':'component_update_not_accepted'}
    class ReplySocket:
        def __init__(self,*a):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def settimeout(self,*a):pass
        def connect(self,*a):pass
        def sendall(self,*a):pass
        def recv(self,*a):return json.dumps(result).encode()+b'\n'
    monkeypatch.setattr(socket,'socket',ReplySocket)
    with pytest.raises(ComponentUpdateNotAccepted):UpdateHelperClient('/unused').component_operation(payload)
