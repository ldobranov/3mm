"""Read-only TLS issuer identity and hot root-route composition, no live devices."""
import copy
from types import SimpleNamespace

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine,select,delete
from sqlalchemy.orm import Session

from backend.db.installation_identity import CoreInstallationIdentity
from backend.services.installation_identity import _load_or_create
from backend.services.installation_session_tls import installation_client_context,current_installation_identity
from backend.services import application_remote_sessions as remote
from three_mm_runtime.tests.test_session_link import certificates


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
