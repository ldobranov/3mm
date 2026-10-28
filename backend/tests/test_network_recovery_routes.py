from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.config import NetworkRecoverySettings
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.user import User
from backend.routes import network_recovery
from backend.routes.network_recovery import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def make_client(tmp_path, monkeypatch):
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
    viewer = User(
        username="viewer",
        email="viewer@example.com",
        hashed_password=hash_password("test-password"),
        role="user",
    )
    db.add_all([admin, viewer])
    db.commit()
    settings = NetworkRecoverySettings(
        policy_file=tmp_path / "policy.json",
        marker_file=tmp_path / "network-recovery.json",
        helper_socket=tmp_path / "helper.sock",
        machine_id_file=tmp_path / "missing-machine-id",
    )
    monkeypatch.setattr(
        network_recovery,
        "get_settings",
        lambda: SimpleNamespace(network_recovery=settings),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return (
        TestClient(app),
        db,
        create_access_token(str(admin.id), {"role": "admin"}),
        create_access_token(str(viewer.id), {"role": "user"}),
    )


def test_status_and_policy_are_admin_only_and_default_to_enabled(
    tmp_path, monkeypatch
) -> None:
    client, db, admin_token, viewer_token = make_client(tmp_path, monkeypatch)
    try:
        assert client.get("/api/v1/network-recovery/status").status_code == 401
        assert client.get(
            "/api/v1/network-recovery/status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        ).status_code == 403

        status = client.get(
            "/api/v1/network-recovery/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        changed = client.put(
            "/api/v1/network-recovery/policy",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"automatic_setup_enabled": False},
        )

        assert status.status_code == 200
        assert status.json()["automatic_setup_enabled"] is True
        assert status.json()["offline_after_seconds"] == 300
        assert status.json()["automatic_setup_available"] is False
        assert status.json()["setup_network"] is None
        assert status.json()["setup_url"].endswith(".local:8895/setup")
        assert status.json()["device_hostname"]
        assert status.json()["local_url"].endswith(".local")
        assert changed.json()["automatic_setup_enabled"] is False
        audit = db.execute(select(AuditLog)).scalar_one()
        assert audit.action == "NETWORK_RECOVERY_POLICY_CHANGED"
    finally:
        db.close()


def test_manual_setup_requires_exact_confirmation_and_uses_fixed_helper_action(
    tmp_path, monkeypatch
) -> None:
    client, db, admin_token, _viewer_token = make_client(tmp_path, monkeypatch)
    calls: list[int] = []

    class FakeClient:
        def __init__(self, _socket):
            pass

        def request_network_setup(self, user_id: int) -> None:
            calls.append(user_id)

    monkeypatch.setattr(network_recovery, "UpdateHelperClient", FakeClient)
    try:
        rejected = client.post(
            "/api/v1/network-recovery/setup",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirmation": "yes"},
        )
        accepted = client.post(
            "/api/v1/network-recovery/setup",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"confirmation": "START SETUP"},
        )

        assert rejected.status_code == 409
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "queued"
        assert accepted.json()["setup_network"] is None
        assert accepted.json()["setup_url"].endswith(".local:8895/setup")
        assert "access_code" not in accepted.json()
        assert not (tmp_path / "setup-access.json").exists()
        assert calls and calls[0] > 0
        audit = db.execute(select(AuditLog)).scalar_one()
        assert audit.action == "NETWORK_SETUP_REQUESTED"
    finally:
        db.close()


def test_ap_requires_admin_interface_and_exact_acknowledgement(tmp_path, monkeypatch):
    client, db, token, viewer = make_client(tmp_path, monkeypatch)
    calls = []
    class Helper:
        def __init__(self, _path): pass
        def request_access_point(self, *args, **kwargs): calls.append((args, kwargs))
    monkeypatch.setattr(network_recovery, "UpdateHelperClient", Helper)
    monkeypatch.setattr(network_recovery, "read_network_recovery_status", lambda _settings:
        SimpleNamespace(access_point={"state":"inactive", "interfaces":["wifi0"]}))
    (tmp_path / "missing-machine-id").write_text("1"*32)
    body={"confirmation":"START ACCESS POINT", "interface":"wifi0", "duration_seconds":300}
    try:
        assert client.post("/api/v1/network-recovery/access-point", json=body).status_code==401
        assert client.post("/api/v1/network-recovery/access-point",json=body,headers={"Authorization":"Bearer "+viewer}).status_code==403
        headers={"Authorization":"Bearer "+token}
        for bad in [{**body,"interface":"wifi0;reboot"},{**body,"duration_seconds":True},{**body,"confirmation":"yes"}]:
            assert client.post("/api/v1/network-recovery/access-point",json=bad,headers=headers).status_code==422
        assert client.post("/api/v1/network-recovery/access-point",json={**body,"interface":"wifi1"},headers=headers).status_code==409
        response=client.post("/api/v1/network-recovery/access-point",json=body,headers=headers)
        assert response.status_code==202 and response.json()["setup_url"]=="http://10.42.0.1:8895/setup"
        assert response.json()["setup_network"].startswith("3mm Setup ")
        assert "access_code" not in response.json()
        assert len(calls)==1 and calls[0][0][0]=="start" and calls[0][1]=={"interface":"wifi0","duration":300}
        identifier=response.json()["id"]
        stop_body={"confirmation":"STOP ACCESS POINT","id":identifier}
        assert client.post("/api/v1/network-recovery/access-point/stop",json=stop_body).status_code==401
        assert client.post("/api/v1/network-recovery/access-point/stop",json=stop_body,headers={"Authorization":"Bearer "+viewer}).status_code==403
        assert len(calls)==1
        stopped=client.post("/api/v1/network-recovery/access-point/stop",json={"confirmation":"STOP ACCESS POINT","id":identifier},headers=headers)
        assert stopped.status_code==202 and calls[-1][0]==("stop",1,identifier)
    finally:db.close()


def test_setup_helper_failure_still_refuses_activation(tmp_path, monkeypatch):
    client, db, token, _viewer=make_client(tmp_path, monkeypatch)
    calls=[]
    class Helper:
        def __init__(self,_path):pass
        def request_network_setup(self, _user_id):
            calls.append('request')
            raise network_recovery.UpdateHelperError('helper unavailable')
    monkeypatch.setattr(network_recovery,"UpdateHelperClient",Helper)
    try:
        result=client.post("/api/v1/network-recovery/setup",headers={"Authorization":"Bearer "+token},json={"confirmation":"START SETUP"})
        assert result.status_code==409 and result.json()=={"detail":"helper unavailable"}
        assert calls==['request']
        assert db.execute(select(AuditLog)).first() is None
    finally:db.close()
