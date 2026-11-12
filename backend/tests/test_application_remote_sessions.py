"""Read-only TLS issuer identity and hot root-route composition, no live devices."""
import copy
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine,select,delete
from sqlalchemy.orm import Session

from backend.db.installation_identity import CoreInstallationIdentity
# Register the user mapper's direct relations for this independently runnable
# database test; collecting another authority suite must not be a prerequisite.
from backend.db.audit_log import AuditLog  # noqa: F401
from backend.db.permission import Permission  # noqa: F401
from backend.db.role import Group,Role  # noqa: F401
from backend.db.session import UserSession  # noqa: F401
from backend.installation.identity import _load_or_create
from backend.installation.session_tls import installation_client_context,current_installation_identity
from backend.applications.sessions import remote
from components.system_runtime.tests.test_session_link import certificates


def test_tls_context_uses_existing_identity_without_creating_or_rewriting_it(tmp_path,monkeypatch,certificates):
    engine=create_engine('sqlite:///'+str(tmp_path/'identity.db'))
    CoreInstallationIdentity.__table__.create(engine)
    monkeypatch.setenv('AI_SETTINGS_MASTER_KEY',Fernet.generate_key().decode())
    try:
        # Explicit creation is confined to this disposable test fixture.
        with Session(engine) as db:
            identity,_key=_load_or_create(db)
            before=db.get(CoreInstallationIdentity,1).encrypted_private_key
        context,expected=installation_client_context(engine,certificates.node_pem.decode())
        assert expected==identity and context.check_hostname
        assert current_installation_identity(engine,expected)
        with Session(engine) as db:
            assert db.get(CoreInstallationIdentity,1).encrypted_private_key==before
            db.execute(delete(CoreInstallationIdentity));db.commit()
        assert not current_installation_identity(engine,expected)
        with pytest.raises(Exception):installation_client_context(engine,certificates.node_pem.decode())
        with Session(engine) as db:assert db.get(CoreInstallationIdentity,1) is None
    finally:engine.dispose()


def test_root_route_reload_is_new_request_only_and_ambiguous_routes_are_unavailable(monkeypatch):
    state={'version':1,'peers':[{'device_id':'one','host':'direct'}]};digest=['first']
    monkeypatch.setattr(remote,'configuration',lambda path:(copy.deepcopy(state),digest[0]))
    class Entry:
        def __init__(self,path,revision,value):self.revision,self.value=revision,value
        def available(self,db,resource):return self.value['device_id']==resource['target_device_id']
        def resolve(self,engine,resource):
            return SimpleNamespace(host=self.value['host'],is_current=lambda:self.revision==digest[0])
    monkeypatch.setattr(remote,'RemoteSessionRuntime',Entry)
    source=remote.ConfiguredRemoteSessions();engine=create_engine('sqlite://')
    try:
        first=source.resolve(engine,{'target_device_id':'one'})
        assert first.host=='direct' and first.is_current()
        state['peers'][0]['host']='loopback-relay';digest[0]='second'
        assert not first.is_current()
        second=source.resolve(engine,{'target_device_id':'one'})
        assert second.host=='loopback-relay' and second.is_current()
        state['peers'].append({'device_id':'one','host':'ambiguous'})
        with pytest.raises(ValueError,match='Ambiguous'):source.resolve(engine,{'target_device_id':'one'})
    finally:engine.dispose()


@pytest.mark.parametrize('host_account',[
    {'resource_profile':'host_account_session_v1','account':'3mm-terminal',
     'uid':1234,'gid':1234,'home':'/var/lib/3mm-terminal','policy_sha256':'c'*64},
    {},
    'host_account_session_v1',
])
def test_remote_route_never_reinterprets_a_host_account_resource(host_account):
    route=remote.RemoteSessionRuntime.__new__(remote.RemoteSessionRuntime)
    def forbidden():
        raise AssertionError('A local host-account review must not inspect a Node route')
    route.current=forbidden
    # The host marker alone must refuse routing, even before other resource
    # fields or a database/TLS route can be read. Malformed host metadata cannot
    # fall through to the isolated executor either.
    assert not route.available(None,{'host_account':host_account})


@pytest.mark.parametrize('explicit_null',[False,True])
def test_remote_route_still_accepts_an_exact_isolated_resource(monkeypatch,explicit_null):
    route=remote.RemoteSessionRuntime.__new__(remote.RemoteSessionRuntime)
    route.value={'device_id':'dev_'+'a'*32,'provider_id':'org.example.terminal',
        'provider_version':'1.0.0','capability_id':'terminal.session',
        'artifact_sha256':'b'*64}
    route.peer_sha256='d'*64
    route.current=lambda:True
    resource={'target_device_id':route.value['device_id'],'provider_version':'1.0.0',
        'declaration':{'provider_id':'org.example.terminal','capability_id':'terminal.session'}}
    if explicit_null:resource['host_account']=None
    device=SimpleNamespace(device_id=route.value['device_id'])
    db=SimpleNamespace(scalar=lambda query:device)
    monkeypatch.setattr(remote,'registered_capabilities',lambda session,current:[{
        'provider_id':route.value['provider_id'],'provider_version':'1.0.0',
        'capability_id':'terminal.session','metadata':{'session_link_sha256':'d'*64,
            'session_provider_sha256':'b'*64,'session_profile':'isolated_session_v1'}}])
    assert route.available(db,resource)
