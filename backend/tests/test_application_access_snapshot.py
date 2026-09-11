from datetime import datetime, timedelta

import pytest

from backend.db.session import UserSession
from backend.tests.test_application_access import environment, headers
from backend.utils.jwt_utils import create_access_token


@pytest.fixture
def setup(monkeypatch, tmp_path):
    values = environment(monkeypatch, tmp_path)
    yield values
    values[0].close()
    values[1].close()
    values[2].dispose()


def test_snapshot_matches_grant_and_revoke_gateway_decisions(setup):
    client, db, engine, admin, user, installation, package, admin_token, token = setup
    base = f"/api/v1/application-extensions/{package.module_id}"
    request = {"payload": {}, "idempotency_key": "access-test-1"}
    result = client.get(base + "/access", headers=headers(token))
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json() == {"module_id": package.module_id, "active_version": package.version,
                             "user_id": user.id, "allowed_route_ids": [], "allowed_operation_ids": []}
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=request).status_code == 403
    assert client.post(base + "/permissions/grants", headers=headers(admin_token),
                       json={"user_id": user.id, "permission_id": "records_manage"}).status_code == 201
    snapshot = client.get(base + "/access", headers=headers(token)).json()
    assert snapshot["allowed_route_ids"] == ["operations"]
    assert snapshot["allowed_operation_ids"] == ["approve"]
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=request).status_code == 200
    assert client.delete(base + f"/permissions/grants/{user.id}/records_manage", headers=headers(admin_token)).status_code == 200
    assert client.get(base + "/access", headers=headers(token)).json()["allowed_operation_ids"] == []
    assert client.post(base + "/operator/operations/approve", headers=headers(token), json=request).status_code == 403
    # A foreign user_id never selects another principal.
    assert client.get(base + f"/access?user_id={admin.id}", headers=headers(token)).json()["user_id"] == user.id


def test_admin_snapshot_excludes_kiosk_and_internal_operations(setup):
    client, _, _, admin, _, installation, package, token, _ = setup
    result = client.get(f"/api/v1/application-extensions/{package.module_id}/access", headers=headers(token))
    assert result.json()["allowed_operation_ids"] == ["approve"]
    assert result.json()["allowed_route_ids"] == ["operations"]


@pytest.mark.parametrize("kind", ["application_kiosk", "device"])
def test_nonhuman_credentials_are_rejected(setup, kind):
    client, _, _, _, user, _, package, _, _ = setup
    token = create_access_token(str(user.id), {"token_type": kind})
    url = f"/api/v1/application-extensions/{package.module_id}/access"
    assert client.get(url, headers=headers(token)).status_code == 401
    assert client.get(url).status_code == 401


def test_disabled_or_missing_installation_is_not_an_empty_success(setup):
    client, db, _, _, _, installation, package, _, token = setup
    installation.enabled = False
    db.commit()
    assert client.get(f"/api/v1/application-extensions/{package.module_id}/access", headers=headers(token)).status_code == 409
    assert client.get("/api/v1/application-extensions/org.example.missing/access", headers=headers(token)).status_code == 404


@pytest.mark.parametrize("state", ["revoked", "expired", "foreign", "missing"])
def test_session_revocation_blocks_snapshot_and_gateway(setup, state):
    client, db, _, admin, user, installation, package, _, _ = setup
    session = UserSession(user_id=user.id, token="session-placeholder", is_active=True,
                          expires_at=datetime.utcnow() + timedelta(hours=1))
    db.add(session)
    db.commit()
    token = create_access_token(str(user.id), {"sid": session.id})
    base = f"/api/v1/application-extensions/{package.module_id}"
    assert client.get(base + "/access", headers=headers(token)).status_code == 200
    if state == "revoked":
        session.is_active = False
    elif state == "expired":
        session.expires_at = datetime.utcnow() - timedelta(hours=1)
    elif state == "foreign":
        session.user_id = admin.id
    else:
        db.delete(session)
    db.commit()
    assert client.get(base + "/access", headers=headers(token)).status_code == 401
    assert client.post(base + "/operator/operations/approve", headers=headers(token),
                       json={"payload": {}, "idempotency_key": "revoked-test"}).status_code == 401
