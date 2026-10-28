"""Normal authenticated Agent onboarding -> fresh consent -> native SDK receipt.

Providers are never inserted into Core SQL by this test. The pre-existing neutral
application fixture supplies package/authority infrastructure, not reader offers.
"""
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import shutil
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from agent.capability_providers import AgentProviderRegistry
from agent.core_client import CorePublisher, CommandJournal, ReconciliationStore, OutboxStore
from agent.device_transport import HttpDeviceTransport, HttpRejected
from agent.hardware.identifier import MockIdentifierAdapter
from agent.tests.test_capability_providers import OtherAdapter
from backend.db.base import Base
from backend.db.device import Device, DeviceCredential, DeviceEvent, DeviceCapabilityProvider, DeviceCapabilityHealth
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationEventDelivery as Delivery, ModulePackage
from backend.routes.device_capabilities import router as providers
from backend.routes.device_events import router as event_router
from backend.services.device_pairing import credential_secret_hash
from backend.services import application_events as broker, application_extensions as gateway
from backend.services import application_authority_management as authority
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.tests.test_application_event_authority import events, core_installed, source_subject, source_installed, replace_package
from backend.tests.test_application_consent import preview, allow
from backend.tests.test_application_authority_sources import DEVICE, CREDENTIAL
from backend.tests.test_application_events import pump
from backend.tests.test_application_public_web_transport import SERVICE, wait_for
from backend.utils.db_utils import get_db
from agent.credentials import DeviceCredential as AgentCredential
from three_mm_runtime.application_transport import ApplicationServiceClient

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='Signed native Unix service and Core authority keys')
AGENT_SECRET = 'a' * 43


def test_actual_admin_discovery_and_configuration_pass_browser_decoder(events, tmp_path, monkeypatch):
    """The owner-facing editor consumes the real APIs used for Agent onboarding."""
    root = Path(__file__).resolve().parents[2]; frontend = root / 'frontend'
    node = shutil.which('node')
    if node is None or not (frontend / 'compiler/node_modules/esbuild').is_dir():
        pytest.skip('Requires the locked compiled UI Node/esbuild toolchain')
    Base.metadata.create_all(events.engine)
    responses = []
    with http_agent(events, monkeypatch) as (client, transport, _credential):
        adapter = OtherAdapter()
        registry = AgentProviderRegistry(tmp_path / 'agent', DEVICE, (adapter,))
        registry.synchronize(transport, availability=True)
        base = f'/api/v1/devices/{DEVICE}'
        headers = {'Authorization': 'Bearer ' + events.token}
        def inspect():
            providers = client.get(base + '/capability-providers', headers=headers)
            offers = client.get(base + '/capabilities?registry_version=3', headers=headers)
            assert providers.status_code == offers.status_code == 200
            responses.append({'providers': providers.json(), 'offers': offers.json()})
        inspect()
        configure(client, events, adapter.provider_declaration())
        inspect()
        configure(client, events, adapter.provider_declaration(), enabled=False)
        inspect()
    script = r'''
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [frontend, output, device] = process.argv.slice(1);
const {build} = createRequire(frontend + '/compiler/package.json')('esbuild');
await build({entryPoints:[frontend + '/src/utils/device-capabilities.ts'],
  outfile:output, bundle:true, format:'esm', platform:'node', logLevel:'silent', plugins:[{
    name:'decoder-only', setup(api) {
      api.onResolve({filter:/^(axios|\.\/auth|\.\/runtime-config)$/}, args => ({path:args.path, namespace:'transport'}));
      api.onLoad({filter:/.*/, namespace:'transport'}, () => ({contents:"export default {}; export const getToken=()=>''; export const getBackendUrl=()=>'';"}));
    }
  }]});
const {readDeviceProvider,readDeviceOffers} = await import(pathToFileURL(output).href);
const responses=JSON.parse(readFileSync(0,'utf8'));
for (const response of responses) {
  for (const provider of response.providers) readDeviceProvider(provider,device);
  readDeviceOffers(response.offers);
}
console.log(JSON.stringify({accepted:responses.length}));
'''
    result = subprocess.run([node, '--input-type=module', '-e', script, str(frontend),
        str(tmp_path / 'capability-decoder.mjs'), DEVICE], input=json.dumps(responses), text=True,
        capture_output=True, cwd=root, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {'accepted': 3}


@contextmanager
def http_agent(s, monkeypatch):
    with s.engine.begin() as db:
        db.execute(update(DeviceCredential).values(secret_hash=credential_secret_hash(AGENT_SECRET)))
    app = FastAPI(); app.include_router(providers); app.include_router(event_router)
    def database():
        with Session(s.engine) as db: yield db
    app.dependency_overrides[get_db] = database
    def enqueue(identifier, *_args):
        with Session(s.engine) as db:
            broker.enqueue_application_event(db, db.get(DeviceEvent, identifier), s.settings)
    monkeypatch.setattr('backend.routes.device_events.process_application_event', enqueue)
    with TestClient(app) as client:
        def bridge(method):
            def request(url, **kwargs):
                result = client.request(method, url.removeprefix('http://core.test'),
                    headers=kwargs.get('headers'), json=kwargs.get('json'))
                class Response:
                    status_code = result.status_code
                    def json(self): return result.json()
                    def raise_for_status(self):
                        if self.status_code >= 400: raise requests.HTTPError(result.text)
                return Response()
            return request
        for method in ('get', 'put', 'post'):
            monkeypatch.setattr('agent.device_transport.requests.'+method, bridge(method))
        credential = AgentCredential(device_id=DEVICE, credential_id=CREDENTIAL, credential_secret=AGENT_SECRET)
        yield client, HttpDeviceTransport('http://core.test', credential), credential


def configure(client, s, declaration, *, enabled=None):
    base = f'/api/v1/devices/{DEVICE}/capability-providers/{declaration.provider_type}/{declaration.provider_id}'
    current = client.get(base, headers={'Authorization':f'Device {CREDENTIAL}:{AGENT_SECRET}'}).json()
    suffix = '/configuration' if enabled is None else '/enabled'
    data = {'expected_revision':current['revision'], **({'capability_ids':[c.capability_id for c in declaration.capabilities]}
        if enabled is None else {'enabled':enabled})}
    response = client.post(base+suffix, headers={'Authorization':'Bearer '+s.token}, json=data)
    assert response.status_code == 200, response.text


def prepare_application(s, module, capability):
    Base.metadata.create_all(s.engine)
    manifest = s.validated.manifest.model_dump(mode='json')
    definition = s.validated.application_extension.model_dump(mode='json')
    manifest['module_id'] = definition['module_id'] = module
    manifest['capabilities']['consumes'].append(capability)
    definition['service']['sdk_version'] = '1.3'
    definition['event_subscriptions'][0]['capability_id'] = capability
    definition['event_subscriptions'][0]['event_type'] = capability
    second = {**definition['event_subscriptions'][0], 'subscription_id':'second_source'}
    definition['event_subscriptions'].append(second)
    definition['optional_resources'] = ['event:changes', 'event:second_source']
    replace_package(s, definition, manifest)
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id==1).values(module_id=module))
        db.execute(update(Installation).where(Installation.id==1).values(module_id=module))


@pytest.mark.parametrize('module,kind', [('org.example.reception','identifier'), ('org.example.monitor','measurement')])
def test_real_onboarding_two_apps_and_adapters_need_no_core_special_case(events, tmp_path, monkeypatch, module, kind):
    s = events
    adapter = MockIdentifierAdapter(tmp_path/'scan.json') if kind == 'identifier' else OtherAdapter()
    declaration = adapter.provider_declaration(); capability = declaration.capabilities[0].capability_id
    prepare_application(s, module, capability)
    assert {i['reason'] for i in preview(s)['unavailable_resources']} == {'capability_unresolved'}
    with http_agent(s, monkeypatch) as (client, transport, credential):
        registry = AgentProviderRegistry(tmp_path/'agent', DEVICE, (adapter,))
        registry.synchronize(transport, availability=True)
        assert not transport.provider(*declaration.identity).configured_capability_ids
        assert {i['reason'] for i in preview(s)['unavailable_resources']} == {'capability_unresolved'}
        configure(client, s, declaration)
        registry.synchronize(transport, availability=True)
        viewed = preview(s)
        assert viewed['unavailable_resources'] == []
        assert all(scope not in viewed['selected_scopes'] for scope in definition_scopes())
        assert 'connector:business_api' in viewed['selected_scopes']
        allow(s, viewed)  # Enforced application, optional events explicitly unselected.
        viewed = preview(s)
        publisher = CorePublisher(core_url='http://core.test', credential=credential, inventory_provider=lambda:None,
            command_journal=CommandJournal(tmp_path/'agent'), reconciliation_store=ReconciliationStore(tmp_path/'agent'),
            outbox=OutboxStore(tmp_path/'agent'), started_monotonic=0, transport=transport)
        def emit():
            event = adapter.scan('TOKEN-1') if kind == 'identifier' else {
                'event_type':capability,'payload':{'capability_id':capability,'value':7}}
            publisher.publish_event(event)
            payload = publisher._event_queue.get_nowait(); publisher._deliver_event(payload)
            return payload
        old = emit()
        allow(s, viewed, scopes=viewed['selected_scopes']+definition_scopes())
        # A real signed native peer uses the public own-SQLite SDK for dedup.
        with tempfile.TemporaryDirectory(prefix='provider-peer-',dir='/tmp') as location:
            root=Path(location); (root/'mode').write_text('valid')
            service = SERVICE.replace("result={'status':200,'content_type':'text/html; charset=utf-8','headers':{},'body':'<h1>Public</h1>'}", "result={}")
            service = service.replace('def handle(connection):', "from three_mm_application_sdk import ApplicationStorage,ApplicationMigration\nstore=ApplicationStorage(root/'data')\nstore.migrate([ApplicationMigration('0001',lambda db:db.execute('CREATE TABLE receipts(event_id TEXT PRIMARY KEY)'))],'0001')\ndef handle(connection):")
            service = service.replace("mode=(root/'mode').read_text()", "with store.transaction() as db:db.execute('INSERT OR IGNORE INTO receipts VALUES (?)',(request['payload']['event_id'],))\n        mode=(root/'mode').read_text()", 1)
            peer=subprocess.Popen([sys.executable,'-c',service,str(root),(b's'*32).hex()],cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                wait_for(lambda:(root/'service.sock').exists())
                with s.engine.begin() as db: db.execute(update(Installation).values(socket_path=str(root/'service.sock')))
                monkeypatch.setattr(gateway,'ApplicationServiceClient',ApplicationServiceClient)
                monkeypatch.setattr(broker,'_send_event_invocation',s.event_sender)
                fresh=emit()
                with Session(s.engine) as db: pump(db,s.settings)
                with sqlite3.connect(root/'data/state.sqlite3') as db:
                    assert db.execute('SELECT event_id FROM receipts').fetchall() == [(fresh['event_id'],)]
                assert old['event_id'] != fresh['event_id']
                with Session(s.engine) as db:
                    delivered=list(db.scalars(select(Delivery).where(Delivery.status=='acknowledged')))
                    assert len(delivered)==2  # Both scopes, one durable SDK receipt.
            finally:
                peer.terminate(); peer.communicate(timeout=5)
        configure(client,s,declaration,enabled=False)
        registry.synchronize(transport,availability=True)
        assert {i['reason'] for i in preview(s)['unavailable_resources']} == {'capability_unresolved'}
        AgentProviderRegistry(tmp_path/'agent',DEVICE,()).synchronize(transport,availability=True)
        assert transport.provider(*declaration.identity).capabilities == ()


def definition_scopes():
    return ['event:changes','event:second_source']


def test_actual_agent_factory_onboards_and_withdraws_its_configured_adapter(events,tmp_path,monkeypatch):
    from agent.main import create_app
    from agent.config import AgentSettings
    from agent.identity import AgentIdentityStore, AgentIdentity
    from agent.credentials import DeviceCredentialStore
    from agent.hardware import HardwareProfile
    from three_mm_protocol import AgentRole
    s=events;prepare_application(s,'org.example.factory','identifier.scan.v1')
    captured=[]
    monkeypatch.setattr(CorePublisher,'start',lambda publisher:captured.append(publisher))
    data=tmp_path/'factory'
    AgentIdentityStore(data)._write(AgentIdentity(device_id=DEVICE,created_at=datetime.now(UTC)))
    with http_agent(s,monkeypatch) as (_,transport,credential):
        DeviceCredentialStore(data).save(credential.model_copy(update={'hub_endpoint':'http://core.test'}))
        for driver in ['mock','disabled']:
            settings=AgentSettings(data_dir=data,role=AgentRole.STANDALONE,core_url='http://core.test',
                hardware_profile=HardwareProfile.MOCK_PI3,identifier_driver=driver)
            with TestClient(create_app(settings)) as client:
                captured[-1].adapter_providers.synchronize(transport,availability=True)
                hello=client.get('/api/v1/agent/hello').json()
                assert ('identifier.scan.v1' in hello['capabilities']) == (driver=='mock')
            row=transport.provider('agent_adapter','identifier.mock')
            assert bool(row.capabilities) == (driver=='mock')


@pytest.mark.parametrize('fault', ['stale_health','unhealthy','revoked','conflict'])
def test_unready_untrusted_sources_cannot_be_approved(events,tmp_path,monkeypatch,fault):
    s=events;adapter=MockIdentifierAdapter(tmp_path/'scan');declaration=adapter.provider_declaration()
    prepare_application(s,'org.example.deny','identifier.scan.v1')
    with http_agent(s,monkeypatch) as (client,transport,_):
        registry=AgentProviderRegistry(tmp_path/'agent',DEVICE,(adapter,));registry.synchronize(transport,availability=True)
        configure(client,s,declaration);registry.synchronize(transport,availability=True)
        viewed=preview(s)
        allow(s,viewed,scopes=viewed['selected_scopes']+definition_scopes())
        viewed=preview(s)
        with Session(s.engine) as db, db.begin():
            if fault=='revoked':db.execute(update(Device).values(revoked_at=datetime.now(UTC)))
            elif fault=='conflict':
                db.add(DeviceCapabilityProvider(device_id=1,provider_type='example',provider_id='conflicting',provider_version='1',
                    revision=1,enabled=True,reported_at=datetime.now(UTC),configured_capability_ids=['identifier.scan.v1'],
                    capabilities=[{'capability_id':'identifier.scan.v1','metadata':{}}]))
            else:
                row=db.scalar(select(DeviceCapabilityHealth).where(DeviceCapabilityHealth.provider_id=='identifier.mock'))
                if fault=='stale_health':row.expires_at=datetime.now(UTC)-timedelta(seconds=1)
                else:row.report={**row.report,'capabilities':[{'capability_id':'identifier.scan.v1','healthy':False}]}
        with pytest.raises(authority.AuthorityManagementError):allow(s,viewed,scopes=viewed['selected_scopes']+definition_scopes())
        with pytest.raises((authority.AuthorityManagementError, AuthorityReviewKeyError)):
            with s.manager.keys.locked() as key, Session(s.engine) as db:
                s.manager._require_grant(db,key,1,s.manager._prepare(1),'event:changes')
        if fault=='revoked':
            # This fixture also has a required command on the revoked device.
            with pytest.raises(authority.AuthorityManagementError): preview(s)
        else:
            assert preview(s)['unavailable_resources']
