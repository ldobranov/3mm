from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401 - register complete model metadata
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.device import DeviceCredential, DevicePairingRequest
from backend.db.user import User
from backend.routes.device_pairing import router
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from backend.utils import jwt_utils


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def make_client() -> tuple[TestClient, Session, str, str]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("test-password"),
        role="admin",
    )
    user = User(
        username="viewer",
        email="viewer@example.com",
        hashed_password=hash_password("test-password"),
        role="user",
    )
    db.add_all([admin, user])
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    admin_token = create_access_token(str(admin.id), {"role": "admin"})
    user_token = create_access_token(str(user.id), {"role": "user"})
    return TestClient(app), db, admin_token, user_token


def test_admin_issues_code_and_agent_claims_pending_request() -> None:
    client, db, admin_token, _ = make_client()
    try:
        issue_response = client.post(
            "/api/v1/pairing-codes",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert issue_response.status_code == 201
        issued = issue_response.json()

        claim_response = client.post(
            "/api/v1/pairing/claim",
            json={
                "code": issued["code"],
                "device_id": "dev_0123456789abcdef0123456789abcdef",
                "public_key": "ssh-ed25519 test-agent-public-key",
                "display_name": "Test Agent",
                "role": "node",
                "protocol_version": "1.0",
            },
        )
        assert claim_response.status_code == 202
        assert claim_response.json() == {
            "request_id": issued["request_id"],
            "status": "pending_approval",
        }
        stored = db.get(DevicePairingRequest, issued["request_id"])
        assert stored is not None
        assert stored.claimed_at is not None
        assert db.query(AuditLog).filter_by(action="PAIRING_CODE_CREATED").count() == 1
    finally:
        db.close()


def test_pairing_code_creation_is_admin_only() -> None:
    client, db, _, user_token = make_client()
    try:
        assert client.post("/api/v1/pairing-codes").status_code == 401
        response = client.post(
            "/api/v1/pairing-codes",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
    finally:
        db.close()


def test_claim_does_not_create_device_and_replay_is_rejected() -> None:
    client, db, admin_token, _ = make_client()
    try:
        issued = client.post(
            "/api/v1/pairing-codes",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        payload = {
            "code": issued["code"],
            "device_id": "dev_0123456789abcdef0123456789abcdef",
            "public_key": "ssh-ed25519 test-agent-public-key",
            "display_name": "Test Agent",
            "role": "node",
            "protocol_version": "1.0",
        }

        assert client.post("/api/v1/pairing/claim", json=payload).status_code == 202
        replay = client.post("/api/v1/pairing/claim", json=payload)
        assert replay.status_code == 400
        assert db.query(DevicePairingRequest).count() == 1
        assert "devices" in Base.metadata.tables
        assert db.execute(Base.metadata.tables["devices"].select()).first() is None
    finally:
        db.close()


def test_admin_explicitly_approves_pending_device_without_issuing_secret() -> None:
    client, db, admin_token, _ = make_client()
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        issued = client.post("/api/v1/pairing-codes", headers=headers).json()
        claim = client.post(
            "/api/v1/pairing/claim",
            json={
                "code": issued["code"],
                "device_id": "dev_0123456789abcdef0123456789abcdef",
                "public_key": "ssh-ed25519 test-agent-public-key",
                "display_name": "Test Agent",
                "role": "node",
                "protocol_version": "1.0",
            },
        )
        assert claim.status_code == 202

        approval = client.post(
            f"/api/v1/pairing/requests/{issued['request_id']}/approve",
            headers=headers,
        )
        assert approval.status_code == 200
        assert approval.json()["status"] == "approved"
        assert "secret" not in approval.text.lower()
        assert (
            db.query(AuditLog).filter_by(action="DEVICE_PAIRING_APPROVED").count() == 1
        )

        duplicate = client.post(
            f"/api/v1/pairing/requests/{issued['request_id']}/approve",
            headers=headers,
        )
        assert duplicate.status_code == 409
    finally:
        db.close()


def test_agent_completes_approved_pairing_and_secret_is_returned_once() -> None:
    client, db, admin_token, _ = make_client()
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        device_id = "dev_0123456789abcdef0123456789abcdef"
        issued = client.post("/api/v1/pairing-codes", headers=headers).json()
        claim_payload = {
            "code": issued["code"],
            "device_id": device_id,
            "public_key": "ssh-ed25519 test-agent-public-key",
            "display_name": "Test Agent",
            "role": "node",
            "protocol_version": "1.0",
        }
        assert (
            client.post("/api/v1/pairing/claim", json=claim_payload).status_code == 202
        )

        completion_payload = {"code": issued["code"], "device_id": device_id}
        premature = client.post("/api/v1/pairing/complete", json=completion_payload)
        assert premature.status_code == 409

        approval = client.post(
            f"/api/v1/pairing/requests/{issued['request_id']}/approve",
            headers=headers,
        )
        assert approval.status_code == 200

        completion = client.post("/api/v1/pairing/complete", json=completion_payload)
        assert completion.status_code == 200
        credential = completion.json()
        assert credential["device_id"] == device_id
        assert credential["credential_id"].startswith("cred_")
        assert len(credential["credential_secret"]) >= 43

        replay = client.post("/api/v1/pairing/complete", json=completion_payload)
        assert replay.status_code == 409
        assert "credential_secret" not in replay.text
    finally:
        db.close()


def test_admin_revokes_issued_device_credential_with_audit_record() -> None:
    client, db, admin_token, _ = make_client()
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        device_id = "dev_0123456789abcdef0123456789abcdef"
        issued = client.post("/api/v1/pairing-codes", headers=headers).json()
        client.post(
            "/api/v1/pairing/claim",
            json={
                "code": issued["code"],
                "device_id": device_id,
                "public_key": "ssh-ed25519 test-agent-public-key",
                "display_name": "Test Agent",
                "role": "node",
                "protocol_version": "1.0",
            },
        )
        client.post(
            f"/api/v1/pairing/requests/{issued['request_id']}/approve",
            headers=headers,
        )
        completed = client.post(
            "/api/v1/pairing/complete",
            json={"code": issued["code"], "device_id": device_id},
        ).json()

        endpoint = (
            f"/api/v1/devices/{device_id}/credentials/"
            f"{completed['credential_id']}/revoke"
        )
        revoked = client.post(endpoint, headers=headers)
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        credential = db.query(DeviceCredential).one()
        assert credential.revoked_at is not None
        assert (
            db.query(AuditLog).filter_by(action="DEVICE_CREDENTIAL_REVOKED").count()
            == 1
        )

        assert client.post(endpoint, headers=headers).status_code == 404
    finally:
        db.close()
