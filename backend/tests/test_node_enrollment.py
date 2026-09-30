from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib

import pytest
import requests

from backend.tests.test_device_pairing_routes import make_client, use_test_jwt_secret
from backend.db.device import Device, DeviceCredential, DevicePairingRequest
from backend.services.node_enrollment import enroll_node
from three_mm_protocol.fleet_pairing import NodeEnrollmentRequest
from agent.enrollment import NodeEnrollmentWorker
from agent.core_client import DeviceCredentialStore


def payload(**overrides):
    return {"device_id": "dev_" + "a" * 32, "display_name": "Zero",
            "request_token": "b" * 64, "credential_id": "cred_" + "c" * 32,
            "credential_secret_hash": hashlib.sha256(b"test-device-secret").hexdigest(),
            **overrides}


def test_enrollment_is_idempotent_private_and_requires_admin_approval():
    client, db, admin, user = make_client()
    try:
        body = payload()
        first = client.post("/api/v1/pairing/enroll", json=body)
        assert first.status_code == 200
        assert first.json()["status"] == "pending_approval"
        assert client.post("/api/v1/pairing/enroll", json=body).json() == first.json()
        assert db.query(DevicePairingRequest).count() == 1
        assert db.query(Device).count() == db.query(DeviceCredential).count() == 0
        row = db.query(DevicePairingRequest).one()
        assert row.created_by_user_id is None
        assert row.code_hash != body["request_token"]
        approve = f"/api/v1/pairing/requests/{row.id}/approve"
        assert client.post(approve, headers={"Authorization": f"Bearer {user}"}).status_code == 403
        assert client.post(approve, headers={"Authorization": f"Bearer {admin}"}).status_code == 200
        for _ in range(2):
            response = client.post("/api/v1/pairing/enroll", json=body)
            assert response.json()["status"] == "approved"
            assert "secret" not in response.text and body["request_token"] not in response.text
        assert db.query(DeviceCredential).count() == 1
        assert db.query(DeviceCredential).one().secret_hash == body["credential_secret_hash"]
        assert client.post("/api/v1/pairing/complete", json={
            "device_id": body["device_id"], "code": body["request_token"],
        }).status_code == 409
        assert client.post("/api/v1/pairing/enroll", json=payload(request_token="d" * 64)).status_code == 409
        credential = db.query(DeviceCredential).one()
        credential.revoked_at = datetime.now(timezone.utc)
        db.commit()
        assert client.post("/api/v1/pairing/enroll", json=body).json()["status"] == "revoked"
        assert db.query(DeviceCredential).count() == 1
    finally:
        db.close()


def test_rejection_persists_and_changed_request_cannot_bypass_it():
    client, db, admin, _ = make_client()
    try:
        body = payload()
        client.post("/api/v1/pairing/enroll", json=body)
        row = db.query(DevicePairingRequest).one()
        assert client.post(f"/api/v1/pairing/requests/{row.id}/reject",
                           headers={"Authorization": f"Bearer {admin}"}).status_code == 204
        assert client.post("/api/v1/pairing/enroll", json=body).json()["status"] == "rejected"
        assert client.post("/api/v1/pairing/enroll", json=payload(credential_id="cred_" + "d" * 32)).status_code == 409
        assert db.query(Device).count() == 0
    finally:
        db.close()


def test_pending_enrollment_expires_without_renewal():
    _, db, _, _ = make_client()
    try:
        now = datetime.now(timezone.utc)
        request = NodeEnrollmentRequest(**payload())
        assert enroll_node(db, request, now=now).status == "pending_approval"
        assert enroll_node(db, request, now=now + timedelta(hours=24)).status == "expired"
        assert db.query(DevicePairingRequest).count() == 1
    finally:
        db.close()


def test_node_worker_recovers_lost_reply_and_restart_through_real_core_routes(tmp_path):
    client, db, admin, _ = make_client()
    from backend.routes.device_ingest import router as ingest_router
    from backend.tests.test_device_ingest_routes import heartbeat_payload
    client.app.include_router(ingest_router)
    approved, statuses = [], []

    class Transport:
        lose_reply = True
        @staticmethod
        def get(url, **kwargs):
            assert url == "http://hub.local/runtime-config.json"
            assert kwargs["allow_redirects"] is False
            return type("Config", (), {"status_code": 200, "json": lambda _: {"backend_port": 8887}})()

        def post(self, url, **kwargs):
            assert url == "http://hub.local:8887/api/v1/pairing/enroll"
            assert (tmp_path / "hub-enrollment.json").exists()
            assert "credential_secret" not in kwargs["json"]
            assert kwargs["allow_redirects"] is False
            response = client.post("/api/v1/pairing/enroll", json=kwargs["json"])
            if self.lose_reply:
                self.lose_reply = False
                raise requests.ConnectionError("lost reply after commit")
            return response

    transport = Transport()
    def worker():
        return NodeEnrollmentWorker(tmp_path, "http://hub.local", "dev_" + "e" * 32,
                                    "Zero", approved.append, statuses.append, transport=transport)
    try:
        with pytest.raises(requests.ConnectionError):
            worker().tick()
        original = (tmp_path / "hub-enrollment.json").read_bytes()
        assert worker().tick() is False
        row = db.query(DevicePairingRequest).one()
        client.post(f"/api/v1/pairing/requests/{row.id}/approve", headers={"Authorization": f"Bearer {admin}"})
        restarted = worker()
        assert restarted.tick() is True
        assert statuses[-1] == "credential_available"
        stored = DeviceCredentialStore(tmp_path).load()
        assert stored == approved[0]
        assert stored.api_endpoint == "http://hub.local:8887"
        assert stored.hub_endpoint == "http://hub.local"
        heartbeat = client.post(f"/api/v1/devices/{stored.device_id}/heartbeat",
            json=heartbeat_payload(stored.device_id),
            headers={"Authorization": f"Device {stored.credential_id}:{stored.credential_secret}"})
        assert heartbeat.status_code == 202
        assert hashlib.sha256(stored.credential_secret.encode()).hexdigest() == db.query(DeviceCredential).one().secret_hash
        assert (tmp_path / "hub-enrollment.json").read_bytes() == original
        # Another retry after approval recovers the SAME key, never a replacement.
        assert worker().tick() is True
        assert approved[1] == approved[0]
        assert db.query(Device).count() == db.query(DeviceCredential).count() == 1
        with pytest.raises(ValueError):
            NodeEnrollmentWorker(tmp_path, "http://other.local", stored.device_id,
                                 "Zero", approved.append, statuses.append, transport=transport).tick()
    finally:
        db.close()
