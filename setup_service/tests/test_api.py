import json
import sqlite3
from dataclasses import replace
from contextlib import contextmanager

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from setup_service.config import SetupSettings
from setup_service.main import PUBLIC_SETUP_ENDPOINTS, create_app
from three_mm_protocol import AgentRole
from three_mm_provisioning import (FileNetworkRecoveryMarker, FileProvisioningStore,
    MemoryProvisioningStore, NetworkMode, ProvisioningSnapshot, ProvisioningState, ProvisioningStoreError)
from three_mm_provisioning.mock_network import MockNetworkAdapter
from three_mm_provisioning.network_helper_client import NetworkHelperClientAdapter
from three_mm_provisioning.setup_access import FileSetupAccessStore
from three_mm_provisioning.setup_journal import SetupJournal, atomic_json
from three_mm_provisioning.network_manager import WifiNetwork
from three_mm_provisioning.wifi_scan_cache import write_wifi_scan_cache


@pytest.fixture
def configuration():
    return dict(network_mode="preserve", locale="bg-BG", device_name="mock-node",
                administrator_name="admin", role="node", hub_endpoint="https://hub.test")


@pytest.fixture
def settings(tmp_path):
    database = tmp_path / "core.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT UNIQUE, "
                           "hashed_password TEXT, role TEXT, is_blocked BOOLEAN DEFAULT 0, token_version INTEGER DEFAULT 0)")
    return SetupSettings(data_dir=tmp_path / "provisioning", core_database_path=database)


@contextmanager
def session(settings, *, network=None, store=None, snapshot=None, recovery=False, interfaces=()):
    store = store or FileProvisioningStore(settings.data_dir)
    if snapshot:
        store.save(snapshot)
    marker = FileNetworkRecoveryMarker(settings.data_dir / "network-recovery.json")
    if recovery:
        marker.activate("manual")
    app = create_app(network, store, settings, marker, capability_provider=lambda: list(interfaces))
    with TestClient(app) as client:
        token = FileSetupAccessStore(settings.data_dir).issue(app.state.setup_runtime.access_snapshot)
        client.headers["Authorization"] = "Bearer " + token
        yield client, store, app.state.setup_runtime


def core_configuration(configuration, **changes):
    result = {**configuration, "role": "standalone", "administrator_email": "admin@example.com",
              "administrator_password": "admin"}
    result.pop("hub_endpoint")
    result.update(changes)
    return result


def wifi_configuration(configuration):
    return {**configuration, "network_mode": "wifi", "network_interface": "wlp2s0",
            "network_name": "private-test-network", "passphrase": "not-a-real-secret"}


def test_surface_and_denied_requests_have_no_side_effects(settings, configuration):
    network = MockNetworkAdapter()
    with session(settings, network=network) as (client, store, runtime):
        assert {(method, route.path) for route in client.app.routes if isinstance(route, APIRoute)
                for method in route.methods} == PUBLIC_SETUP_ENDPOINTS
        client.headers.clear()
        for path in ("prefill", "capabilities", "networks", "diagnostics"):
            assert client.get("/api/v1/setup/" + path).status_code == 401
        assert client.post("/api/v1/setup/configure", json=configuration).status_code == 401
        assert client.post("/api/v1/setup/finish", json={}).status_code == 401
        page = client.get("/setup")
        assert page.status_code == 200
        assert 'result is unconfirmed' in page.text
        assert page.headers['cache-control'] == 'no-store'
        assert page.headers['referrer-policy'] == 'no-referrer'
        assert client.get('/ready').status_code == 200
        assert store.load() is None
        assert network.calls == []


@pytest.mark.parametrize('probe', ['/generate_204', '/hotspot-detect.html', '/connecttest.txt', '/ncsi.txt'])
def test_captive_portal_probes_redirect(settings, probe):
    with session(settings) as (client, _, __):
        response = client.get(probe, follow_redirects=False)
        assert response.status_code == 307 and response.headers['location'] == '/setup'


@pytest.mark.parametrize('kind', ['wrong', 'expired', 'revoked', 'other_device'])
def test_access_denial_and_isolation(settings, configuration, tmp_path, kind):
    with session(settings) as (client, store, runtime):
        if kind == 'wrong':
            client.headers['Authorization'] = 'Bearer ' + 'x' * 43
        elif kind == 'expired':
            value = json.loads(runtime.access.path.read_text())
            value['expires'] = 0
            atomic_json(runtime.access.path, value)
        elif kind == 'revoked':
            runtime.access.revoke()
        else:
            client.headers['Authorization'] = 'Bearer ' + FileSetupAccessStore(tmp_path / 'other').issue(None)
        assert client.post('/api/v1/setup/configure', json=configuration).status_code == 401
        assert store.load() is None
        assert not runtime.journal.path.exists()


@pytest.mark.parametrize('role', ['standalone', 'hub'])
@pytest.mark.parametrize('mode', ['preserve', 'local'])
def test_core_first_admin_and_no_wifi_dependency(settings, configuration, role, mode):
    value = core_configuration(configuration, role=role, network_mode=mode)
    with session(settings) as (client, store, runtime):
        response = client.post('/api/v1/setup/configure', json=value)
        if role == 'hub' and mode == 'local':
            assert response.status_code == 422
            assert store.load() is None
            return
        assert response.status_code == 200, response.text
        assert store.load().network_mode.value == mode
        assert store.load().role.value == role
        assert not runtime.journal.path.exists()
        assert client.get('/api/v1/setup/prefill').status_code == 401
        with sqlite3.connect(settings.core_database_path) as db:
            user = db.execute('SELECT username,email,hashed_password,role FROM users').fetchone()
        from backend.utils.auth import verify_password
        assert user[:2] == ('admin','admin@example.com') and user[3] == 'admin'
        assert verify_password('admin', user[2])


def test_node_no_core_database_or_admin_import(settings, configuration, monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert not name.startswith('backend'), name
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    settings = replace(settings, core_database_path=settings.data_dir / 'missing.db')
    with session(settings) as (client, store, _):
        response = client.post('/api/v1/setup/configure', json=configuration)
        assert response.status_code == 200, response.text
        assert response.json()['enrollment'] == 'awaiting_pairing'
        assert store.load().hub_endpoint == 'https://hub.test'
        assert not settings.core_database_path.exists()


@pytest.mark.parametrize('change', [dict(hub_endpoint='http://user:secret@hub.test'), dict(hub_endpoint=''),
    dict(hub_endpoint='https://hub.test/?secret=123'), dict(network_name='secret'),
    dict(network_mode='local'), dict(administrator_password='secret')])
def test_invalid_choices_never_echo_secrets(settings, configuration, change):
    with session(settings) as (client, store, runtime):
        response = client.post('/api/v1/setup/configure', json={**configuration, **change})
        assert response.status_code == 422
        assert 'secret' not in response.text
        assert store.load() is None and not runtime.journal.path.exists()


def snapshot():
    return ProvisioningSnapshot(state=ProvisioningState.PROVISIONED, role=AgentRole.NODE,
        locale='bg-BG', device_name='mock-node', administrator_name='admin', hub_endpoint='https://hub.test')


@pytest.mark.parametrize('change', [dict(role='hub', hub_endpoint=None), dict(device_name='different'),
    dict(hub_endpoint='https://another.test'), dict(administrator_password='new-secret')])
def test_recovery_cannot_change_identity_or_administrator(settings, configuration, change):
    previous = snapshot()
    with session(settings, snapshot=previous, recovery=True) as (client, store, runtime):
        response = client.post('/api/v1/setup/configure', json={**configuration, **change})
        assert response.status_code in {409, 422}
        assert store.load() == previous and runtime.marker.is_active()


def test_finish_recovery_preserves_journal_and_revokes_code(settings):
    previous = snapshot()
    with session(settings, snapshot=previous, recovery=True) as (client, store, runtime):
        before = store.path.read_bytes()
        assert client.post('/api/v1/setup/finish', json={}).status_code == 200
        assert store.path.read_bytes() == before
        assert not runtime.marker.is_active()
        assert client.post('/api/v1/setup/finish', json={}).status_code == 401


def test_existing_provisioned_device_requires_recovery_marker(settings, configuration):
    with session(settings, snapshot=snapshot()) as (client, store, runtime):
        assert client.post('/api/v1/setup/configure', json=configuration).status_code == 409
        assert client.post('/api/v1/setup/finish', json={}).status_code == 409


def test_network_recovery_preserves_legacy_node_without_reassigning_a_hub(settings, configuration):
    previous=replace(snapshot(),hub_endpoint=None)
    with session(settings,snapshot=previous,recovery=True) as (client,store,runtime):
        response=client.post('/api/v1/setup/configure',json={**configuration,'hub_endpoint':None})
        assert response.status_code==200, response.text
        assert store.load()==previous
        assert response.json()['enrollment']=='preserved'


@pytest.mark.parametrize('failure', ['activate_staged', 'commit', 'verification', 'persistence'])
def test_wifi_failure_restores_previous_snapshot(settings, configuration, failure):
    previous = snapshot()
    network = MockNetworkAdapter(connectivity_succeeds=failure!='verification',
                                 fail_operation=failure if failure in {'activate_staged','commit'} else None)
    class FailingStore(FileProvisioningStore):
        def save(self, value):
            if failure == 'persistence' and value.network_mode is NetworkMode.WIFI:
                raise ProvisioningStoreError('simulated disk failure')
            super().save(value)
    with session(settings, snapshot=previous, recovery=True, network=network,
                 store=FailingStore(settings.data_dir), interfaces=[dict(name='wlp2s0', access_point=False)]) as (client, store, runtime):
        response = client.post('/api/v1/setup/configure', json=wifi_configuration(configuration))
        assert response.status_code in {409,503}, response.text
        assert 'not-a-real-secret' not in response.text and 'private-test-network' not in response.text
        assert store.load() == previous and runtime.marker.is_active()
        assert 'rollback' in network.calls
        assert not runtime.journal.path.exists()


def test_wifi_success_persists_ownership_but_no_credentials(settings, configuration):
    with session(settings, network=MockNetworkAdapter(), interfaces=[dict(name='wlp2s0',access_point=False)]) as (client, store, runtime):
        response = client.post('/api/v1/setup/configure', json=wifi_configuration(configuration))
        assert response.status_code == 200, response.text
        assert store.load().network_mode is NetworkMode.WIFI
        assert store.load().network_interface == 'wlp2s0'
        contents=''.join(path.read_text() for path in settings.data_dir.glob('*.json'))
        assert 'private-test-network' not in contents and 'not-a-real-secret' not in contents


def test_wifi_unavailable_denied_before_staging(settings, configuration):
    network=MockNetworkAdapter()
    with session(settings, network=network) as (client, store, runtime):
        assert client.get('/api/v1/setup/capabilities').json()['network_modes'] == ['preserve','local']
        assert client.post('/api/v1/setup/configure',json=wifi_configuration(configuration)).status_code == 409
        assert network.calls == [] and store.load() is None


def test_busy_request_does_not_start_another_attempt(settings, configuration):
    with session(settings) as (client, store, runtime):
        with runtime.lock:
            assert client.post('/api/v1/setup/configure',json=configuration).status_code == 409
        assert store.load() is None


@pytest.mark.parametrize('saved', [None, snapshot()])
def test_readonly_is_nonmutating(settings, configuration, saved):
    class Forbidden:
        def __getattr__(self,name):
            raise AssertionError(name)
    with session(replace(settings,read_only=True),network=Forbidden(),snapshot=saved,recovery=True) as (client, store, runtime):
        before = store.load()
        assert client.get('/ready').status_code == 200
        assert client.get('/api/v1/setup/networks').json() == {'items':[]}
        assert client.post('/api/v1/setup/configure',json=configuration).status_code == 403
        assert store.load() == before and runtime.marker.is_active()


def test_scan_merges_cache_and_filters_setup_ssid(settings):
    class Scan(MockNetworkAdapter):
        def scan_wifi_networks(self):
            return (WifiNetwork('Cafe',45,False), WifiNetwork('3mm Setup CDEF',100,False))
    write_wifi_scan_cache(settings.data_dir,(WifiNetwork('Hidden',81,True), WifiNetwork('Cafe',30,False)))
    with session(settings,network=Scan(),interfaces=[dict(name='wlp2s0',access_point=True)]) as (client,_,__):
        assert client.get('/api/v1/setup/networks').json()['items'] == [
            dict(network_name='Hidden',signal=81,secured=True),dict(network_name='Cafe',signal=45,secured=False)]


def test_diagnostics_are_opt_in_bounded_metadata(settings, configuration):
    with session(replace(settings,diagnostics=True)) as (client,store,runtime):
        assert client.post('/api/v1/setup/configure',json=configuration).status_code == 200
        with runtime.diagnostics.export() as chunks:
            payload=b''.join(chunks).decode()
        assert 'device.setup' in payload and 'setup.persist' in payload
        assert 'hub.test' not in payload and 'admin' not in payload and 'mock-node' not in payload
        assert runtime.diagnostics.status()['spool_bytes'] == 0


@pytest.mark.parametrize('phase', ['verified','committed','unavailable'])
def test_restart_reconciles_network_receipt_and_hides_uncommitted_role(settings, configuration, phase):
    store=FileProvisioningStore(settings.data_dir)
    journal=SetupJournal(settings.data_dir)
    journal.begin('a'*32,None,wifi=True)
    store.save(snapshot())
    assert store.load_runtime_snapshot() is None
    class Receipt(NetworkHelperClientAdapter):
        def transaction_phase(self,identifier):
            if phase=='unavailable': raise OSError('offline')
            return phase
        def rollback_attempt(self,identifier):
            return 'rolled_back'
    app=create_app(Receipt(settings.data_dir/'missing.sock'),store,settings)
    with TestClient(app):
        runtime=app.state.setup_runtime
        assert runtime.pending is (phase=='unavailable')
        if phase=='committed': assert store.load() == snapshot() and journal.load() is not None
        elif phase=='verified': assert store.load() is None and journal.load() is None
        else: assert store.load_runtime_snapshot() is None and journal.load() is not None


def test_restart_after_recovery_commit_never_repeats_pairing(settings):
    previous=snapshot()
    store=FileProvisioningStore(settings.data_dir)
    store.save(replace(previous,network_mode=NetworkMode.WIFI,network_interface='wlp2s0'))
    SetupJournal(settings.data_dir).begin('a'*32,previous,wifi=True)
    FileNetworkRecoveryMarker(settings.data_dir/'network-recovery.json').activate('manual')
    calls=[]
    class Receipt(NetworkHelperClientAdapter):
        def transaction_phase(self,identifier): return 'committed'
        def activate_runtime(self,*,recovery): calls.append(recovery)
    app=create_app(Receipt(settings.data_dir/'unused.sock'),store,settings)
    with TestClient(app) as client:
        client.headers['Authorization']='Bearer '+FileSetupAccessStore(settings.data_dir).issue(store.load_runtime_snapshot())
        assert client.post('/api/v1/setup/finish',json={}).status_code==200
    assert calls==[True]


def test_oversized_authenticated_body_is_rejected_without_writes(settings):
    with session(settings) as (client,store,runtime):
        response=client.post('/api/v1/setup/configure',content='x'*17000,
                             headers={'Content-Type':'application/json'})
        assert response.status_code==413
        assert store.load() is None and runtime.journal.load() is None


def test_setup_theme_uses_safe_values_from_the_core_database(tmp_path):
    store = MemoryProvisioningStore()
    database = tmp_path / "core.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE settings (id INTEGER PRIMARY KEY, key TEXT, value TEXT)"
        )
        connection.executemany(
            "INSERT INTO settings (key, value) VALUES (?, ?)",
            [
                ("user_theme", "dark"),
                ("dark_body_bg", "#101820"),
                ("dark_card_bg", "#18242f"),
                ("dark_button_primary_bg", "#4caf50"),
                ("header_bg_color", "not-a-color"),
            ],
        )
    settings = SetupSettings(
        data_dir=tmp_path / "provisioning",
        core_database_path=database,
    )

    with TestClient(create_app(MockNetworkAdapter(), store, settings)) as client:
        response = client.get("/api/v1/setup/theme")

    assert response.status_code == 200
    assert response.json()["mode"] == "dark"
    assert response.json()["body_bg"] == "#101820"
    assert response.json()["card_bg"] == "#18242f"
    assert response.json()["primary"] == "#4caf50"
    assert response.json()["header_bg"] == "#4caf50"
