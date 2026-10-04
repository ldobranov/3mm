"""C12/C13 common Core authority/lifecycle, no live hardware or Fleet extension."""

import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from backend.tests.test_device_pairing_routes import make_client
from backend.routes import device_platform, device_commands, device_state, device_ingest
from backend.db.device import (
    Device,
    DeviceCredential,
    DeviceCommand,
    DevicePairingRequest,
    DeviceEvent,
)
from backend.services.device_commands import (
    queue_command,
    deliver_next_command,
    DeviceCommandError,
)
from backend.services.device_platform import platform_snapshot
from backend.utils import jwt_utils
from agent.core_client import DeviceCredential as ClientCredential
from agent.device_transport import HttpDeviceTransport, HttpRejected
from three_mm_protocol.device_platform import (
    challenge,
    AuthorityProofV1,
    verify_authority,
    LifecycleReportV1,
)
from three_mm_protocol.device_authority import DeviceAuthorityStore
from examples.mock_embedded.client import MockEmbeddedClient


@pytest.fixture
def core(monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_MASTER_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "authority-test-key-at-least-32-bytes")
    client, db, admin, viewer = make_client()
    for router in (
        device_platform.router,
        device_commands.router,
        device_state.router,
        device_ingest.router,
    ):
        client.app.include_router(router)
    yield client, db, {"Authorization": "Bearer " + admin}, {
        "Authorization": "Bearer " + viewer
    }
    client.close()
    engine = db.get_bind()
    db.close()
    engine.dispose()


def paired(core):
    client, db, admin, _ = core
    credential = ClientCredential(
        device_id="dev_" + "a" * 32,
        credential_id="cred_" + "b" * 32,
        credential_secret="s" * 43,
    )
    request = dict(
        device_id=credential.device_id,
        credential_id=credential.credential_id,
        display_name="Generic node",
        request_token="c" * 64,
        credential_secret_hash=hashlib.sha256(
            credential.credential_secret.encode()
        ).hexdigest(),
    )
    assert (
        client.post("/api/v1/pairing/enroll", json=request).json()["status"]
        == "pending_approval"
    )
    pending = db.scalar(select(DevicePairingRequest))
    assert (
        client.post(
            f"/api/v1/pairing/requests/{pending.id}/approve", headers=admin
        ).status_code
        == 200
    )
    device = db.scalar(select(Device))
    return credential, device, request


def bind_http(monkeypatch, client):
    def send(method, url, **kwargs):
        kwargs.pop("timeout", None)
        kwargs.pop("allow_redirects", None)
        return client.request(method, urlsplit(url).path, **kwargs)

    for method in ("get", "post", "put"):
        monkeypatch.setattr(
            "agent.device_transport.requests." + method,
            lambda url, method=method, **kwargs: send(method, url, **kwargs),
        )


def test_signed_management_preserves_identity_and_refuses_copied_credential_other_hub(
    core, monkeypatch, tmp_path
):
    credential, device, _ = paired(core)
    client, db, _, _ = core
    bind_http(monkeypatch, client)
    store = DeviceAuthorityStore(
        tmp_path, credential.device_id, credential.credential_id
    )
    transport = HttpDeviceTransport("http://hub-a", credential, authority_store=store)
    assert transport.receive_command() is None
    old_pin = store.load()
    command = queue_command(
        db,
        device=device,
        command_type="agent.ping",
        payload={},
        idempotency_key="test",
        ttl_seconds=60,
    )
    db.commit()
    received = transport.receive_command()
    assert received.command_id == command.command_id
    assert transport.desired_state().device_id == credential.device_id
    # Endpoint change with the SAME key does not transfer trust.
    same = HttpDeviceTransport(
        "http://another-address", credential, authority_store=store
    )
    assert same.platform().installation == old_pin.installation
    from backend.db.installation_identity import CoreInstallationIdentity

    db.delete(db.get(CoreInstallationIdentity, 1))
    db.commit()  # Simulate unrelated Hub B with even the copied device credentials.
    other = HttpDeviceTransport("http://hub-b", credential, authority_store=store)
    with pytest.raises(HttpRejected, match="authority"):
        other.receive_command()
    assert store.load() == old_pin


def test_fresh_nonce_payload_tampering_and_expiry_are_rejected(core, tmp_path):
    credential, _, _ = paired(core)
    client, _, _, _ = core
    request = challenge(credential.device_id, credential.credential_id, "identity")
    proof = AuthorityProofV1.model_validate(
        client.post(
            "/api/v1/pairing/authority-proof", json=request.model_dump(mode="json")
        ).json()
    )
    store = DeviceAuthorityStore(
        tmp_path, credential.device_id, credential.credential_id
    )
    store.verify(proof, request, bootstrap=True)
    with pytest.raises(ValueError, match="challenge"):
        store.verify(
            proof, challenge(credential.device_id, credential.credential_id, "identity")
        )
    changed = proof.model_copy(update={"payload": {"authorized": True}})
    with pytest.raises(ValueError, match="signature"):
        store.verify(changed, request)
    with pytest.raises(ValueError, match="expired"):
        verify_authority(
            proof,
            request,
            proof.identity,
            now=request.expires_at + timedelta(seconds=1),
        )
    wrong = challenge(credential.device_id, credential.credential_id, "command")
    assert (
        client.post(
            "/api/v1/pairing/authority-proof", json=wrong.model_dump(mode="json")
        ).status_code
        == 403
    )


def test_active_offline_recovery_and_release_do_not_erase_or_replay(core):
    credential, device, enroll = paired(core)
    client, db, admin, viewer = core
    prefix = "/api/v1/devices/" + credential.device_id
    headers = {
        "Authorization": f"Device {credential.credential_id}:{credential.credential_secret}"
    }
    snapshot = client.get(prefix + "/platform", headers=admin).json()
    assert (snapshot["lifecycle"], snapshot["connectivity"]) == ("active", "offline")
    pending = queue_command(
        db,
        device=device,
        command_type="agent.ping",
        payload={},
        idempotency_key="pending",
        ttl_seconds=60,
    )
    delivered = queue_command(
        db,
        device=device,
        command_type="agent.ping",
        payload={},
        idempotency_key="delivered",
        ttl_seconds=60,
    )
    db.commit()
    dispatched = deliver_next_command(db, device=device)
    assert dispatched.command_id == pending.command_id
    report = LifecycleReportV1(
        device_id=device.device_id,
        lifecycle="recovery",
        expected_revision=0,
        reason="runtime.unavailable",
    )
    recovered = client.put(
        prefix + "/lifecycle", headers=headers, json=report.model_dump(mode="json")
    )
    assert recovered.status_code == 200
    with pytest.raises(DeviceCommandError, match="recovery"):
        queue_command(
            db,
            device=device,
            command_type="agent.ping",
            payload={},
            idempotency_key="unsafe",
            ttl_seconds=60,
        )
    db.rollback()
    release = {"confirmed_device_id": device.device_id, "expected_revision": 1}
    assert client.post(prefix + "/authority/release", json=release).status_code == 401
    assert (
        client.post(
            prefix + "/authority/release", headers=viewer, json=release
        ).status_code
        == 403
    )
    result = client.post(prefix + "/authority/release", headers=admin, json=release)
    assert result.status_code == 200
    assert result.json()["lifecycle"] == "unowned"
    db.refresh(pending)
    db.refresh(delivered)
    assert (
        pending.status == "delivered"
    )  # Uncertain dispatch retained, never cancelled/replayed.
    assert delivered.result == {"execution_state": "not_dispatched"}
    request = challenge(device.device_id, credential.credential_id, "command")
    assert (
        client.post(
            prefix + "/authority-exchange",
            headers=headers,
            json=request.model_dump(mode="json"),
        ).status_code
        == 401
    )
    assert (
        client.post("/api/v1/pairing/enroll", json=enroll).json()["status"] == "revoked"
    )
    assert (
        db.scalar(
            select(DeviceEvent).where(
                DeviceEvent.event_type == "device.authority.released"
            )
        )
        is not None
    )
    # Explicit admin prepare + NEW credential + second explicit approval.
    assert (
        client.post(
            prefix + "/authority/prepare-enrollment",
            headers=admin,
            json={**release, "expected_revision": 2},
        ).status_code
        == 200
    )
    new = {
        **enroll,
        "credential_id": "cred_" + "d" * 32,
        "request_token": "e" * 64,
        "credential_secret_hash": hashlib.sha256(b"new-private-secret" * 3).hexdigest(),
    }
    assert (
        client.post("/api/v1/pairing/enroll", json=new).json()["status"]
        == "pending_approval"
    )
    pending_request = db.scalar(
        select(DevicePairingRequest).where(
            DevicePairingRequest.requested_device_id == device.device_id
        )
    )
    assert (
        client.post(
            f"/api/v1/pairing/requests/{pending_request.id}/approve", headers=admin
        ).status_code
        == 200
    )
    assert (
        client.get(prefix + "/platform", headers=admin).json()["lifecycle"] == "active"
    )
    assert db.query(Device).count() == 1
    assert (
        client.post(
            prefix + "/authority-exchange",
            headers=headers,
            json=request.model_dump(mode="json"),
        ).status_code
        == 401
    )


def test_mock_runtime_uses_same_authority_and_lifecycle_without_agent_modules(
    core, tmp_path
):
    client, db, admin, _ = core

    class Transport:
        def request(self, method, url, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("allow_redirects", None)
            return client.request(method, urlsplit(url).path, **kwargs)

    node = MockEmbeddedClient("http://hub", tmp_path, transport=Transport())
    try:
        assert node.enroll() == "pending_approval"
        pending = db.scalar(select(DevicePairingRequest))
        assert (
            client.post(
                f"/api/v1/pairing/requests/{pending.id}/approve", headers=admin
            ).status_code
            == 200
        )
        node.heartbeat()
        assert node.platform().connectivity == "online"
        assert node.authority_store.load().installation == node.platform().installation
        assert node.poll() is None
        node.reconcile()
        report = LifecycleReportV1(
            device_id=node.device_id,
            lifecycle="degraded",
            expected_revision=0,
            reason="provider.unavailable",
        )
        assert node.report_lifecycle(report)["lifecycle"] == "degraded"
        old_id = node.device_id
    finally:
        node.close()
    restarted = MockEmbeddedClient("http://hub", tmp_path, transport=Transport())
    try:
        assert restarted.device_id == old_id
        assert restarted.platform().lifecycle == "degraded"
    finally:
        restarted.close()


def test_pinned_transport_cannot_downgrade_to_unsigned_core(
    core, monkeypatch, tmp_path
):
    credential, _, _ = paired(core)
    client, _, _, _ = core
    bind_http(monkeypatch, client)
    store = DeviceAuthorityStore(
        tmp_path, credential.device_id, credential.credential_id
    )
    transport = HttpDeviceTransport("http://hub", credential, authority_store=store)
    assert transport.receive_command() is None

    class Missing:
        status_code = 404

    monkeypatch.setattr(
        "agent.device_transport.requests.post", lambda *a, **k: Missing()
    )
    restarted = HttpDeviceTransport("http://hub", credential, authority_store=store)
    with pytest.raises(HttpRejected, match="authority"):
        restarted.receive_command()


def test_mock_local_reset_preserves_identity_and_receipts_but_rotates_credential(
    core, tmp_path
):
    client, db, admin, _ = core

    class Transport:
        def request(self, method, url, **kwargs):
            kwargs.pop("timeout", None)
            kwargs.pop("allow_redirects", None)
            return client.request(method, urlsplit(url).path, **kwargs)

    node = MockEmbeddedClient("http://hub", tmp_path, transport=Transport())
    try:
        assert node.enroll() == "pending_approval"
        pending = db.scalar(select(DevicePairingRequest))
        assert (
            client.post(
                f"/api/v1/pairing/requests/{pending.id}/approve", headers=admin
            ).status_code
            == 200
        )
        node.heartbeat()
        old_id, old_credential = node.device_id, node.identity["credential_id"]
        with node.db:
            node._enqueue("event", "/events", {"old": "evidence"})
            node.db.execute(
                "INSERT INTO receipts VALUES ('one','cmd_old','digest','{}')"
            )
        archive = node.reset_authority(node.device_id)
        assert archive.is_dir()
        with pytest.raises(ValueError, match="reset/rotation"):
            node.platform()
    finally:
        node.close()
    new = MockEmbeddedClient("http://other-hub", tmp_path, transport=Transport())
    try:
        assert new.device_id == old_id
        assert new.identity["credential_id"] != old_credential
        assert new.pending_count == 0
        assert new.db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 1
        assert (
            new.db.execute(
                "SELECT count(*) FROM state WHERE key LIKE 'released.%'"
            ).fetchone()[0]
            == 1
        )
    finally:
        new.close()
