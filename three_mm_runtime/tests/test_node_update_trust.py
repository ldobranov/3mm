"""Hub approval provenance and explicit pinning, without live devices or changes."""
import base64
from datetime import UTC, datetime, timedelta
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from deployment.trust_node_update_hub import fetch_approval_key, normalize_hub
from three_mm_protocol.node_updates import (
    NodeUpdateApplyRequest, NodeUpdateApprovalKey, NodeUpdateAuthorization,
    canonical_node_update_authorization,
)
from three_mm_runtime import node_update_trust as module
from three_mm_runtime.node_update_helper import NodeUpdateError, NodeUpdateHelper, NodeUpdateStore


@pytest.fixture
def signed(tmp_path, monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    key = NodeUpdateApprovalKey(key_id=hashlib.sha256(public).hexdigest(),
        public_key=base64.b64encode(public).decode())
    created = datetime.now(UTC)
    request = NodeUpdateApplyRequest(operation_id="nodeupd_" + "1" * 32,
        device_id="dev_" + "a" * 32, release_id="v1.2.0", archive_sha256="b" * 64,
        confirmed_install=True, created_at=created, expires_at=created + timedelta(seconds=120))
    approval = NodeUpdateAuthorization(request=request, key_id=key.key_id,
        signature=base64.b64encode(private.sign(canonical_node_update_authorization(request, key.key_id))).decode())
    executable = tmp_path / "openssl"
    executable.write_bytes(b"fixture executable")
    monkeypatch.setattr(module, "OPENSSL", executable)
    trust = tmp_path / "trust.json"
    module.pin_approval_key(key, key.key_id, device_id=request.device_id, trust_file=trust, enforce_permissions=False)
    return key, approval, trust, tmp_path


def verification_runner(argv, **kwargs):
    assert argv[1:6] == ["pkeyutl", "-verify", "-pubin", "-keyform", "DER"]
    assert "-rawin" in argv and kwargs["timeout"] == 5
    assert kwargs["env"] == {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "OPENSSL_CONF": "/dev/null"}
    key = serialization.load_der_public_key(Path(argv[argv.index("-inkey") + 1]).read_bytes())
    message = Path(argv[argv.index("-in") + 1]).read_bytes()
    signature = Path(argv[argv.index("-sigfile") + 1]).read_bytes()
    try:
        key.verify(signature, message)
    except InvalidSignature:
        return SimpleNamespace(returncode=1)
    return SimpleNamespace(returncode=0)


def verify(signed, approval=None):
    _, original, trust, root = signed
    return module.verify_node_update_authorization(approval or original,
        state_root=root, trust_file=trust, enforce_permissions=False, runner=verification_runner)


def test_valid_approval_uses_pinned_key_and_cleans_private_verification_files(signed):
    verify(signed)
    assert not list(signed[3].glob(".approval-*"))


def test_actual_openssl_ed25519_verification_when_available(signed, monkeypatch):
    executable = Path("/usr/bin/openssl") if os.name == "posix" else Path("C:/Program Files/Git/usr/bin/openssl.exe")
    if not executable.is_file():
        pytest.skip("OpenSSL executable is not available on this test host")
    monkeypatch.setattr(module, "OPENSSL", executable)
    _, approval, trust, root = signed
    module.verify_node_update_authorization(approval, state_root=root,
        trust_file=trust, enforce_permissions=False)
    with pytest.raises(NodeUpdateError) as error:
        module.verify_node_update_authorization(approval.model_copy(update={
            "request": approval.request.model_copy(update={"release_id": "v1.4.0"})}),
            state_root=root, trust_file=trust, enforce_permissions=False)
    assert error.value.code == "invalid_approval"


@pytest.mark.parametrize("change", ["release_id", "archive_sha256", "device_id", "expires_at", "signature"])
def test_signed_fields_cannot_be_replaced_by_service_caller(signed, change):
    approval = signed[1]
    changes = {"release_id": "v1.3.0", "archive_sha256": "c" * 64,
        "device_id": "dev_" + "d" * 32, "expires_at": approval.request.expires_at - timedelta(seconds=1)}
    altered = (approval.model_copy(update={"signature": base64.b64encode(b"x" * 64).decode()})
               if change == "signature" else approval.model_copy(update={"request": approval.request.model_copy(update={change: changes[change]})}))
    with pytest.raises(NodeUpdateError) as error:
        verify(signed, altered)
    assert error.value.code == ("identity_mismatch" if change == "device_id" else "invalid_approval")


def test_unknown_key_missing_pin_and_unsigned_apply_fail_closed(signed):
    approval = signed[1]
    with pytest.raises(NodeUpdateError) as error:
        verify(signed, approval.model_copy(update={"key_id": "e" * 64}))
    assert error.value.code == "untrusted_hub"
    signed[2].unlink()
    with pytest.raises(NodeUpdateError) as error:
        verify(signed)
    assert error.value.code == "hub_trust_missing"
    store = NodeUpdateStore(signed[3] / "state", enforce_permissions=False)
    helper = NodeUpdateHelper(store, service_uid=1000,
        validator=lambda _: pytest.fail("unsigned request reached archive validator"))
    result = helper.handle_request({"action": "apply", "request": approval.request.model_dump(mode="json")}, peer_uid=0)
    assert result == {"ok": False, "error": "invalid_request"}
    assert store.records() == []


def test_pin_is_explicit_repeatable_and_refuses_different_key(signed):
    key, _, trust, _ = signed
    device_id = signed[1].request.device_id
    assert module.pin_approval_key(key, key.key_id, device_id=device_id, trust_file=trust, enforce_permissions=False) is False
    with pytest.raises(NodeUpdateError) as error:
        module.pin_approval_key(key, "0" * 64, device_id=device_id, trust_file=trust, enforce_permissions=False)
    assert error.value.code == "fingerprint_mismatch"
    different = b"d" * 32
    changed = NodeUpdateApprovalKey(key_id=hashlib.sha256(different).hexdigest(), public_key=base64.b64encode(different).decode())
    with pytest.raises(NodeUpdateError) as error:
        module.pin_approval_key(changed, changed.key_id, device_id=device_id, trust_file=trust, enforce_permissions=False)
    assert error.value.code == "hub_trust_conflict"
    assert module.read_approval_key(trust, enforce_permissions=False) == key
    with pytest.raises(NodeUpdateError) as error:
        module.pin_approval_key(key, key.key_id, device_id="dev_" + "f" * 32,
            trust_file=trust, enforce_permissions=False)
    assert error.value.code == "hub_trust_conflict"


def test_invalid_pinned_file_is_not_a_replacement_opportunity(signed):
    key, _, trust, _ = signed
    trust.write_text("{}")
    with pytest.raises(NodeUpdateError) as error:
        module.pin_approval_key(key, key.key_id, device_id=signed[1].request.device_id, trust_file=trust, enforce_permissions=False)
    assert error.value.code == "invalid_trust"


def test_bootstrap_fetch_is_fixed_bounded_and_does_not_follow_redirects(signed):
    key = signed[0]
    calls = []

    class Response:
        status_code = 200
        headers = {}
        data = key.model_dump_json().encode()
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, chunk_size):
            assert chunk_size == 1024
            yield self.data

    class Session:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    session = Session()
    assert fetch_approval_key("http://rasp-3mm.local/", session=session) == key
    assert session.trust_env is False
    assert calls == [("http://rasp-3mm.local/api/v1/devices/node-updates/approval-key",
        {"timeout": (5, 10), "allow_redirects": False, "stream": True,
         "headers": {"Accept-Encoding": "identity"}})]
    Response.status_code = 302
    with pytest.raises(ValueError, match="HTTP 200"):
        fetch_approval_key("http://rasp-3mm.local", session=session)
    Response.status_code, Response.data = 200, b"x" * 4097
    with pytest.raises(ValueError, match="too large"):
        fetch_approval_key("http://rasp-3mm.local", session=session)


@pytest.mark.parametrize("url", ["http://example.com", "http://user:pass@hub.local", "http://hub.local/path", "file:///etc/passwd", "https://hub.local?key=other"])
def test_bootstrap_rejects_unsafe_origin(url):
    with pytest.raises(ValueError):
        normalize_hub(url)


def test_support_requires_safe_pin_but_allows_explicit_unconfigured_state(signed, monkeypatch):
    store = NodeUpdateStore(signed[3] / "state", enforce_permissions=False)
    helper = NodeUpdateHelper(store, service_uid=1000)
    trust = module.read_node_update_trust(signed[2], enforce_permissions=False)
    monkeypatch.setattr(module, "read_node_update_trust", lambda: trust)
    assert helper.handle_request({"action": "support"}, peer_uid=1000)["support"] == {
        "schema_version": 1, "signed_apply_supported": True,
        "approval_key_id": signed[0].key_id, "trusted_device_id": signed[1].request.device_id}
    def missing(): raise NodeUpdateError("hub_trust_missing", "not pinned")
    monkeypatch.setattr(module, "read_node_update_trust", missing)
    assert helper.handle_request({"action": "support"}, peer_uid=1000)["support"]["approval_key_id"] is None
    def invalid(): raise NodeUpdateError("invalid_trust", "bad pin")
    monkeypatch.setattr(module, "read_node_update_trust", invalid)
    assert helper.handle_request({"action": "support"}, peer_uid=1000) == {"ok": False, "error": "invalid_trust"}
