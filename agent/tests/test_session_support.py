import json
import os
import time

import pytest
from agent import session_support


@pytest.fixture
def support(tmp_path,monkeypatch):
    root=tmp_path/'executor';root.mkdir(mode=0o755);path=root/'support.json'
    monkeypatch.setattr(session_support,'SUPPORT',path)
    value={'version':1,'device_id':'dev_'+'a'*32,'generation':'b'*32,'expires_at':time.time()+8,
           'component':'session-node','build_id':'c'*64,'pid':os.getpid()}
    path.write_text(json.dumps(value));path.chmod(0o644)
    return path,value


def test_fresh_optional_component_only_advertises_support_for_its_device(support):
    path,value=support
    assert session_support.session_link_available(value['device_id'])
    assert not session_support.session_link_available('dev_'+'f'*32)


@pytest.mark.parametrize('change',[{'expires_at':0},{'expires_at':time.time()+1000},{'version':True},
    {'component':'other'},{'extra':'field'},{'pid':True}])
def test_stale_invalid_or_unrelated_support_never_enables_feature(support,change):
    path,value=support;path.write_text(json.dumps({**value,**change}))
    assert not session_support.session_link_available(value['device_id'])


def test_missing_symlink_or_writable_support_is_unavailable(support):
    path,value=support;path.chmod(0o666)
    assert not session_support.session_link_available(value['device_id'])
    path.unlink();assert not session_support.session_link_available(value['device_id'])
    target=path.with_suffix('.other');target.write_text(json.dumps(value));path.symlink_to(target)
    assert not session_support.session_link_available(value['device_id'])
