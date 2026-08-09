import json
import stat

import pytest

from agent.identity import AgentIdentityStore, IdentityStoreError


def test_identity_is_persistent_and_private(tmp_path):
    store = AgentIdentityStore(tmp_path)

    first = store.load_or_create()
    second = AgentIdentityStore(tmp_path).load_or_create()

    assert second == first
    assert first.device_id.startswith("dev_")
    assert len(first.device_id) == 36
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_separate_data_directories_get_different_identities(tmp_path):
    first = AgentIdentityStore(tmp_path / "first").load_or_create()
    second = AgentIdentityStore(tmp_path / "second").load_or_create()

    assert first.device_id != second.device_id


def test_corrupt_identity_fails_instead_of_silently_replacing_it(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps({"device_id": "broken"}), encoding="utf-8")

    with pytest.raises(IdentityStoreError):
        AgentIdentityStore(tmp_path).load_or_create()

    assert json.loads(identity_path.read_text(encoding="utf-8")) == {
        "device_id": "broken"
    }
