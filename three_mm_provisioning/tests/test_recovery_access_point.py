from pathlib import Path
import os
import uuid
import pytest
from three_mm_protocol import AgentRole
from three_mm_provisioning.models import ProvisioningState
from three_mm_provisioning.persistence import FileProvisioningStore, ProvisioningSnapshot
from three_mm_provisioning.network import NetworkAdapterError
from three_mm_provisioning.recovery_access_point import RecoveryAccessPoint, read_status
from three_mm_provisioning.setup_journal import atomic_json

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX shared transaction lock')
PREVIOUS = '11111111-1111-4111-8111-111111111111'
NEW = '22222222-2222-4222-8222-222222222222'
SESSION = 'a' * 32

class Boundary:
    def __init__(self):
        self.current = PREVIOUS
        self.profiles = {PREVIOUS: 'host-owned'}
        self.events = []
        self.timer_fails = self.activation_fails = self.restore_fails = False
    def active_connection_uuid(self, interface):
        return self.current or '--'
    def schedule_access_point_stop(self, identifier, duration):
        self.events.append(('timer', identifier, duration))
        if self.timer_fails: raise NetworkAdapterError('timer unavailable')
    def create_temporary_open_setup_access_point(self, **values):
        self.events.append(('ap', values))
        self.current = values['connection_uuid']
        self.profiles[self.current] = values['connection_name']
        if self.activation_fails: raise NetworkAdapterError('activation lost')
    def has_local_address(self, _interface): return True
    def connection_uuid(self, value):
        if value in self.profiles: return value
        return next((key for key, name in self.profiles.items() if name == value), None)
    def restore_connection(self, value):
        self.events.append(('restore', value))
        if self.restore_fails: raise NetworkAdapterError('original network absent')
        self.current = value
    def delete_connection(self, value):
        self.events.append(('delete', value))
        self.profiles.pop(value, None)
        if self.current == value: self.current = None

@pytest.fixture
def prepared(tmp_path):
    data = tmp_path/'provisioning'
    FileProvisioningStore(data).save(ProvisioningSnapshot(
        state=ProvisioningState.PROVISIONED, role=AgentRole.STANDALONE,
        locale='en', device_name='existing-device', administrator_name='owner'))
    before = {p.name:p.read_bytes() for p in data.iterdir() if p.is_file()}
    boundary = Boundary()
    ap = RecoveryAccessPoint(tmp_path/'root', boundary=boundary, provisioning=data,
        status_path=tmp_path/'run/status.json', interfaces=lambda:[{'name':'wifi0','access_point':True}],
        network_name='3mm Setup TEST', clock=lambda:1000)
    return ap, boundary, data, before

def test_timer_precedes_radio_and_role_identity_remain_unchanged(prepared):
    ap,boundary,data,before=prepared
    result=ap.start('wifi0', SESSION, 300)
    assert result['state']=='active' and result['expires_at']==1300
    assert [event[0] for event in boundary.events][:2]==['timer','ap']
    assert boundary.events[1][1]['ipv4_address']=='10.42.0.1/24'
    ap.stop(SESSION)
    assert boundary.current==PREVIOUS and list(boundary.profiles)==[PREVIOUS]
    assert {p.name:p.read_bytes() for p in data.iterdir() if p.is_file()}==before
    assert read_status(ap.status_path)['state']=='inactive'
    assert ap.path.stat().st_mode & 0o077 == 0

@pytest.mark.parametrize('failure',['timer','activation'])
def test_failed_start_compensates_and_never_mutates_before_timer(prepared,failure):
    ap,boundary,_,_=prepared
    setattr(boundary, failure+'_fails', True)
    with pytest.raises(NetworkAdapterError):ap.start('wifi0',SESSION)
    assert boundary.current==PREVIOUS and list(boundary.profiles)==[PREVIOUS]
    if failure=='timer':assert all(event[0]!='ap' for event in boundary.events)

def test_stale_timer_cannot_close_current_ap(prepared):
    ap,boundary,_,_=prepared
    ap.start('wifi0',SESSION)
    profile=boundary.current
    ap.stop('b'*32)
    assert boundary.current==profile and read_status(ap.status_path)['state']=='active'
    with pytest.raises(ValueError,match='already pending'):ap.start('wifi0','c'*32)

def test_committed_new_wifi_wins_over_original(prepared):
    ap,boundary,_,_=prepared
    ap.start('wifi0',SESSION); profile=boundary.current
    boundary.profiles[NEW]='3mm-wifi';boundary.current=NEW
    atomic_json(ap.transaction.path,dict(id='b'*32,interface='wifi0',previous=profile,
        old_owned=None,owned={},staged=NEW,deadline=1200,phase='committed',finalized=True))
    ap.stop(SESSION)
    assert boundary.current==NEW and NEW in boundary.profiles and profile not in boundary.profiles
    assert ('restore',PREVIOUS) not in boundary.events

def test_unconfirmed_wifi_is_rolled_back_before_ap_profile_is_removed(prepared):
    ap,boundary,_,_=prepared
    ap.start('wifi0',SESSION); profile=boundary.current
    boundary.profiles[NEW]='3mm-staged';boundary.current=NEW
    atomic_json(ap.transaction.path,dict(id='b'*32,interface='wifi0',previous=profile,
        old_owned=None,owned={},staged=NEW,deadline=1200,phase='verified',finalized=False))
    ap.stop(SESSION)
    assert boundary.current==PREVIOUS and NEW not in boundary.profiles and profile not in boundary.profiles
    value=ap.transaction._load()
    assert value['phase']=='rolled_back' and value['previous']==PREVIOUS

def test_restart_recovery_and_missing_previous_network_leave_no_autoconnect_ap(prepared):
    ap,boundary,_,_=prepared
    ap.start('wifi0',SESSION);profile=boundary.current
    restarted=RecoveryAccessPoint(ap.path.parent,boundary=boundary,status_path=ap.status_path)
    boundary.restore_fails=True
    with pytest.raises(NetworkAdapterError):restarted.recover()
    assert profile not in boundary.profiles and read_status(ap.status_path)['state']=='failed'
    boundary.restore_fails=False
    restarted.recover()
    assert boundary.current==PREVIOUS and read_status(ap.status_path)['state']=='inactive'

def test_pending_wifi_transaction_blocks_ap(prepared):
    ap,boundary,_,_=prepared
    atomic_json(ap.transaction.path,dict(id='b'*32,interface='wifi0',previous=PREVIOUS,
        old_owned=None,owned={},staged=None,deadline=1200,phase='applying',finalized=False))
    with pytest.raises(ValueError,match='transaction is pending'):ap.start('wifi0',SESSION)
    assert boundary.events==[]

@pytest.mark.parametrize('interface,identifier,duration',[('wifi0;reboot',SESSION,300),('wifi0','bad',300),('wifi0',SESSION,True),('wifi0',SESSION,901)])
def test_malformed_ap_request_cannot_mutate(prepared,interface,identifier,duration):
    ap,boundary,_,_=prepared
    with pytest.raises(ValueError):ap.start(interface,identifier,duration)
    assert boundary.events==[]

def test_overlapping_setup_subnet_reports_failure_before_radio(monkeypatch):
    import json
    import sys
    import three_mm_provisioning.recovery_access_point as module
    state = dict(state='starting', id=SESSION, interface='wifi0', expires_at=1300,
                 network='3mm Setup TEST', setup_url=module.AP_URL, reason=None)
    class UnusedController:
        def __init__(self, **kwargs): pass
        def start(self, *args): raise AssertionError('Radio must remain untouched')
    published = []
    monkeypatch.setattr(module, 'RecoveryAccessPoint', UnusedController)
    monkeypatch.setattr(module.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(module, 'read_status', lambda: dict(state))
    monkeypatch.setattr(module, 'publish_status', published.append)
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *a, **k:
                        json.dumps([{'dst': '10.42.0.0/24', 'dev': 'other0'}]))
    monkeypatch.setattr(sys, 'argv', ['recovery_access_point', 'start', '--interface', 'wifi0', '--id', SESSION])
    with pytest.raises(ValueError, match='overlaps'):
        module.main()
    assert published == [{**state, 'state': 'failed', 'reason': 'start_unconfirmed'}]
