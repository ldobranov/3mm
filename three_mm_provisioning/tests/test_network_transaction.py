import json
import os
from dataclasses import replace

import pytest

from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.network_helper import _handle_request
from three_mm_provisioning.network_transaction import NetworkTransaction

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Root helper requires POSIX locks')
ATTEMPT = 'a' * 32


class PowerLoss(BaseException):
    pass


class Boundary:
    def __init__(self, previous='os-profile', crash=None):
        self.active = previous
        self.profiles = {'3mm-wifi': 'old-owned', 'os-profile': previous}
        self.calls = []
        self.crash = crash
        self.has_ip = True
        self.next_uuid = 'new-profile'

    def active_connection_uuid(self, interface):
        return self.active or '--'

    def connection_uuid(self, name):
        if name in self.profiles.values():
            return name
        return self.profiles.get(name)

    def schedule_setup_rollback(self, identifier):
        self.calls.append(('timer',identifier))
        if self.crash == 'timer': raise PowerLoss()

    def connect_persistent_wifi(self, **values):
        assert values['autoconnect'] is False
        self.profiles[values['connection_name']] = self.next_uuid
        self.active = self.next_uuid
        self.calls.append(('connect',))
        if self.crash == 'connect': raise PowerLoss()

    def has_local_address(self, interface):
        return self.has_ip

    def rename_connection(self, uuid, name):
        self.profiles[name] = uuid
        self.calls.append(('rename',))
        if self.crash == 'rename': raise PowerLoss()

    def set_autoconnect(self, uuid, enabled):
        self.calls.append(('autoconnect',uuid,enabled))
        if self.crash == 'autoconnect': raise PowerLoss()

    def delete_connection(self, uuid):
        self.calls.append(('delete',uuid))
        self.profiles = {name:value for name,value in self.profiles.items() if value!=uuid}
        if self.active == uuid: self.active = None

    def restore_connection(self, uuid):
        self.calls.append(('restore',uuid))
        self.active = uuid


def apply(transaction, identifier=ATTEMPT):
    return transaction.handle(dict(action='wifi.apply', id=identifier, interface='wlp2s0',
                                   network_name='private-network', passphrase='private-passphrase'))


def transaction(tmp_path, boundary, validate=lambda value: None):
    return NetworkTransaction(tmp_path, boundary, validate)


def test_verified_is_provisional_and_foreign_attempt_cannot_commit(tmp_path):
    boundary=Boundary()
    service=transaction(tmp_path,boundary)
    assert apply(service) == {'ok':True,'phase':'verified'}
    assert service.handle(dict(action='wifi.commit',id='b'*32))['phase'] == 'missing'
    with pytest.raises(NetworkAdapterError): apply(service,'b'*32)
    assert not any(call[0]=='autoconnect' for call in boundary.calls)
    assert service.handle(dict(action='wifi.commit',id=ATTEMPT))['phase']=='committed'
    assert ('autoconnect','new-profile',True) in boundary.calls
    assert ('delete','os-profile') not in boundary.calls
    # Matching a display name alone is not proof that 3mm owns a profile.
    assert ('delete','old-owned') not in boundary.calls
    payload=service.path.read_text()
    assert 'private-network' not in payload and 'private-passphrase' not in payload
    assert service.path.stat().st_mode & 0o777 == 0o600
    # An old timer cannot undo a durable commit.
    assert service.handle(dict(action='wifi.rollback',id=ATTEMPT))['phase']=='committed'
    assert boundary.active == 'new-profile'


def test_owned_profile_cleanup_is_scoped_to_the_selected_adapter(tmp_path):
    boundary=Boundary(); service=transaction(tmp_path,boundary)
    apply(service)
    service.handle(dict(action='wifi.commit',id=ATTEMPT))
    boundary.next_uuid='adapter-two'
    service.handle(dict(action='wifi.apply',id='b'*32,interface='wlan9',network_name='other',passphrase='password-two'))
    service.handle(dict(action='wifi.commit',id='b'*32))
    assert ('delete','new-profile') not in boundary.calls
    boundary.next_uuid='adapter-one-next'
    service.handle(dict(action='wifi.apply',id='c'*32,interface='wlp2s0',network_name='third',passphrase='password-three'))
    service.handle(dict(action='wifi.commit',id='c'*32))
    assert ('delete','new-profile') in boundary.calls
    assert ('delete','adapter-two') not in boundary.calls


@pytest.mark.parametrize('previous',[None,'os-profile'])
@pytest.mark.parametrize('crash',['timer','connect','rename'])
def test_interruption_before_commit_restores_previous_link_on_startup(tmp_path,previous,crash):
    boundary=Boundary(previous,crash)
    service=transaction(tmp_path,boundary)
    with pytest.raises(PowerLoss):
        apply(service)
        service.handle(dict(action='wifi.commit',id=ATTEMPT))
    boundary.crash=None
    transaction(tmp_path,boundary).recover()
    assert boundary.active == previous
    assert service.handle(dict(action='wifi.status',id=ATTEMPT))['phase']=='rolled_back'
    assert not any(value=='new-profile' for value in boundary.profiles.values())


def test_restart_finishes_durable_commit_intent(tmp_path):
    boundary=Boundary(crash='autoconnect')
    service=transaction(tmp_path,boundary)
    apply(service)
    with pytest.raises(PowerLoss): service.handle(dict(action='wifi.commit',id=ATTEMPT))
    assert json.loads(service.path.read_text())['phase']=='committed'
    boundary.crash=None
    transaction(tmp_path,boundary).recover()
    assert boundary.active=='new-profile'
    assert ('autoconnect','new-profile',True) in boundary.calls


def test_no_local_ip_rolls_back_without_an_internet_probe(tmp_path):
    boundary=Boundary(); boundary.has_ip=False
    service=transaction(tmp_path,boundary)
    with pytest.raises(NetworkAdapterError): apply(service)
    assert boundary.active=='os-profile'
    assert json.loads(service.path.read_text())['phase']=='rolled_back'


def test_rollback_retries_after_delete_succeeded_but_restore_was_interrupted(tmp_path):
    boundary=Boundary(); service=transaction(tmp_path,boundary)
    apply(service)
    original=boundary.restore_connection
    boundary.restore_connection=lambda uuid: (_ for _ in ()).throw(NetworkAdapterError('NM stopped'))
    with pytest.raises(NetworkAdapterError): service.handle(dict(action='wifi.rollback',id=ATTEMPT))
    assert boundary.active is None
    boundary.restore_connection=original
    service.recover()
    assert boundary.active=='os-profile'


def test_timer_and_commit_deadline_restore_previous_link(tmp_path,monkeypatch):
    boundary=Boundary(); service=transaction(tmp_path,boundary)
    apply(service)
    deadline=json.loads(service.path.read_text())['deadline']
    monkeypatch.setattr('three_mm_provisioning.network_transaction.time.time',lambda:deadline+1)
    assert service.handle(dict(action='wifi.commit',id=ATTEMPT))['phase']=='rolled_back'
    assert boundary.active=='os-profile'


def test_disappearing_adapter_cannot_commit(tmp_path):
    boundary=Boundary(); available=True
    def validate(value):
        if not available: raise NetworkAdapterError('adapter absent')
    service=transaction(tmp_path,boundary,validate)
    apply(service); available=False
    with pytest.raises(NetworkAdapterError): service.handle(dict(action='wifi.commit',id=ATTEMPT))
    service.handle(dict(action='wifi.rollback',id=ATTEMPT))
    assert boundary.active=='os-profile'


@pytest.mark.parametrize('lost_reply', [False, True])
def test_portal_and_root_helper_reconcile_a_commit_reply_loss(tmp_path, lost_reply):
    from fastapi.testclient import TestClient
    from setup_service.main import create_app
    from setup_service.config import SetupSettings
    from three_mm_provisioning.persistence import FileProvisioningStore
    from three_mm_provisioning.network_helper_client import NetworkHelperClientAdapter
    from three_mm_provisioning.setup_access import FileSetupAccessStore

    boundary = Boundary()
    root = transaction(tmp_path / 'root-owned', boundary)
    class Bridge(NetworkHelperClientAdapter):
        drop_reply = lost_reply
        def _request(self, payload):
            if payload['action'] == 'activate_runtime':
                assert payload['recovery'] is False
                return {'ok': True}
            response = _handle_request(payload, root)
            if payload['action'] == 'wifi.commit' and self.drop_reply:
                self.drop_reply = False
                raise NetworkAdapterError('lost response')
            return response
    settings = SetupSettings(data_dir=tmp_path / 'portal')
    store = FileProvisioningStore(settings.data_dir)
    app = create_app(Bridge(tmp_path/'unused.sock'), store, settings,
                     capability_provider=lambda:[dict(name='wlp2s0', access_point=False)])
    with TestClient(app) as client:
        code = FileSetupAccessStore(settings.data_dir).issue(None)
        client.headers['Authorization']='Bearer '+code
        response=client.post('/api/v1/setup/configure',json=dict(role='node',hub_endpoint='https://hub.test',
            locale='en-US',device_name='node',administrator_name='operator',network_mode='wifi',
            network_interface='wlp2s0',network_name='private-network',passphrase='private-passphrase'))
        if lost_reply:
            assert response.status_code==409 and response.json()['detail']=='setup_pending'
            assert store.load_runtime_snapshot() is None
            assert client.post('/api/v1/setup/finish',json={}).status_code==200
        else:
            assert response.status_code==200, response.text
        assert store.load_runtime_snapshot().role.value=='node'
        assert boundary.active=='new-profile'
        assert client.post('/api/v1/setup/finish',json={}).status_code==401
    # The HTTP acknowledgement cannot acknowledge a separate OS activation.
    # Restart the portal with the committed handoff still pending, then resume
    # activation without repeating Wi-Fi or changing the selected identity.
    from three_mm_provisioning.setup_journal import SetupActivationJournal
    activation = SetupActivationJournal(settings.data_dir)
    pending = activation.load()
    assert pending['committed'] is True
    saved_network = root.path.read_bytes()
    restarted = create_app(Bridge(tmp_path/'unused.sock'), store, settings,
        capability_provider=lambda:[dict(name='wlp2s0', access_point=False)])
    with TestClient(restarted) as client:
        token = FileSetupAccessStore(settings.data_dir).issue(store.load_runtime_snapshot())
        client.headers['Authorization'] = 'Bearer '+token
        assert client.get('/api/v1/setup/capabilities').json()['complete'] is True
        assert client.post('/api/v1/setup/finish',json={}).status_code == 200
    assert activation.load() == pending
    assert root.path.read_bytes() == saved_network
    assert store.load_runtime_snapshot().role.value == 'node'


def test_pending_attempt_does_not_start_ap_or_an_uncommitted_role(tmp_path):
    from three_mm_provisioning.persistence import FileProvisioningStore, ProvisioningSnapshot
    from three_mm_provisioning.models import ProvisioningState
    from three_mm_protocol import AgentRole
    from three_mm_provisioning.setup_journal import SetupJournal
    from three_mm_runtime.services import DeviceRuntimePlanner, SetupAccess, RuntimeService
    from three_mm_runtime.install_profile import NetworkBackend
    store=FileProvisioningStore(tmp_path)
    SetupJournal(tmp_path).begin(ATTEMPT,None,wifi=True)
    store.save(ProvisioningSnapshot(state=ProvisioningState.PROVISIONED,role=AgentRole.HUB,
               locale='en-US',device_name='hub',administrator_name='admin'))
    plan=DeviceRuntimePlanner(store,network_backend=NetworkBackend.NETWORK_MANAGER).resolve()
    assert plan.setup_access is SetupAccess.LOCAL
    assert plan.role is None and plan.services==(RuntimeService.SETUP,)


@pytest.mark.parametrize('payload',[None,[],{},dict(action='wifi.apply',id=ATTEMPT),
    dict(action='wifi.commit',id='../../etc/passwd'),dict(action='activate_runtime',recovery='true'),
    dict(action='wifi.apply',id=ATTEMPT,interface='--bad',network_name='x',passphrase='password')])
def test_helper_denies_malformed_requests(tmp_path,payload):
    assert _handle_request(payload,transaction(tmp_path,Boundary()))==dict(ok=False,error='invalid_request')
