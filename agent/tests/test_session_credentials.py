import json
import os

import pytest
from agent.credentials import DeviceCredential,DeviceCredentialStore


def stored(tmp_path):
    root=tmp_path/'agent';root.mkdir(mode=0o700)
    store=DeviceCredentialStore(root)
    value=DeviceCredential(device_id='dev_'+'a'*32,credential_id='cred_'+'b'*32,credential_secret='s'*64,
        hub_endpoint='http://hub.example:8887',api_endpoint='http://hub.example:8887')
    store.save(value)
    return store,value


def test_read_only_component_loads_existing_split_binding_without_chmod(tmp_path,monkeypatch):
    store,value=stored(tmp_path)
    before={p:p.read_bytes() for p in (store.path,store.binding_path)}
    assert 'api_endpoint' not in json.loads(store.path.read_bytes())
    monkeypatch.setattr(os,'chmod',lambda *args:(_ for _ in ()).throw(AssertionError('Read-only loader wrote permissions')))
    assert store.load(read_only=True)==value
    assert all(p.read_bytes()==data for p,data in before.items())


def test_read_only_component_refuses_foreign_binding_or_unsafe_permissions(tmp_path):
    store,value=stored(tmp_path)
    binding=json.loads(store.binding_path.read_bytes());binding['device_id']='dev_'+'f'*32;store.binding_path.write_text(json.dumps(binding))
    with pytest.raises(RuntimeError):store.load(read_only=True)
    store.save(value);store.path.chmod(0o644)
    with pytest.raises(RuntimeError):store.load(read_only=True)
