"""Real account-session endpoints keep current login and owner isolation."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from backend.accounts.sessions.api import router
from backend.db.session import UserSession
from backend.tests.test_session_lifecycle import make_client, use_test_jwt_secret
from backend.accounts.tokens import create_access_token


def tracked_session(db, user, name):
    session = UserSession(
        user_id=user.id,
        token="pending-" + name,
        device_name=name,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        last_activity=datetime(2020, 1, 1),
    )
    db.add(session)
    db.flush()
    token = create_access_token(str(user.id), {
        "sid": session.id, "token_version": user.token_version, "role": user.role,
    })
    session.token = token
    db.commit()
    return session, {"Authorization": "Bearer " + token}


@pytest.fixture
def sessions():
    client, db, foreign_user, owner = make_client()
    client.app.include_router(router, prefix="/api")
    current, headers = tracked_session(db, owner, "current-owner")
    other, other_headers = tracked_session(db, owner, "other-owner")
    foreign, foreign_headers = tracked_session(db, foreign_user, "foreign-user")
    try:
        yield SimpleNamespace(client=client, db=db, owner=owner,
            current=current, other=other, foreign=foreign, headers=headers,
            other_headers=other_headers, foreign_headers=foreign_headers)
    finally:
        engine = db.get_bind()
        client.close()
        db.close()
        engine.dispose()


@pytest.mark.parametrize("fault", ["anonymous", "blocked", "revoked", "replaced_login"])
def test_session_endpoints_refuse_invalid_current_login_without_mutation(sessions, fault):
    s = sessions
    if fault == "blocked":
        s.owner.is_blocked = True
    elif fault == "revoked":
        s.current.is_active = False
    elif fault == "replaced_login":
        s.current.token = create_access_token(str(s.owner.id), {
            "sid": s.current.id, "token_version": s.owner.token_version,
        })
    s.db.commit()
    before = [(row.id, row.is_active, row.last_activity) for row in
        s.db.scalars(select(UserSession).order_by(UserSession.id))]
    headers = {} if fault == "anonymous" else s.headers
    for method, path in (
        ("GET", "/api/sessions/my"),
        ("POST", "/api/sessions/logout-all"),
        ("DELETE", f"/api/sessions/{s.other.id}"),
        ("POST", "/api/sessions/track-activity"),
    ):
        response = s.client.request(method, path, headers=headers)
        assert response.status_code == 401, response.text
    after = [(row.id, row.is_active, row.last_activity) for row in
        s.db.scalars(select(UserSession).order_by(UserSession.id))]
    assert after == before


def test_session_listing_and_revocation_are_scoped_to_the_current_owner(sessions):
    s = sessions
    listing = s.client.get("/api/sessions/my", headers=s.headers)
    assert listing.status_code == 200
    assert {row["id"] for row in listing.json()} == {s.current.id, s.other.id}
    assert all(row["user_id"] == s.owner.id and "token" not in row for row in listing.json())
    response = s.client.delete(f"/api/sessions/{s.foreign.id}", headers=s.headers)
    assert response.status_code == 404
    assert s.db.get(UserSession, s.foreign.id).is_active is True
    assert s.client.delete(f"/api/sessions/{s.other.id}", headers=s.headers).status_code == 200
    assert s.client.get("/api/sessions/my", headers=s.other_headers).status_code == 401
    assert s.client.get("/api/sessions/my", headers=s.headers).status_code == 200
    assert s.client.get("/api/sessions/my", headers=s.foreign_headers).status_code == 200


def test_logout_all_preserves_current_login_and_other_users_sessions(sessions):
    s = sessions
    response = s.client.post("/api/sessions/logout-all", headers=s.headers)
    assert response.status_code == 200
    assert s.db.get(UserSession, s.current.id).is_active is True
    assert s.db.get(UserSession, s.other.id).is_active is False
    assert s.db.get(UserSession, s.foreign.id).is_active is True
    assert s.client.get("/api/sessions/my", headers=s.headers).status_code == 200
    assert s.client.get("/api/sessions/my", headers=s.other_headers).status_code == 401
    assert s.client.get("/api/sessions/my", headers=s.foreign_headers).status_code == 200


def test_activity_updates_only_the_authenticated_session(sessions):
    s = sessions
    before = datetime.utcnow()
    response = s.client.post("/api/sessions/track-activity", headers=s.headers)
    assert response.status_code == 200
    assert s.db.get(UserSession, s.current.id).last_activity >= before
    assert s.db.get(UserSession, s.other.id).last_activity == datetime(2020, 1, 1)
    assert s.db.get(UserSession, s.foreign.id).last_activity == datetime(2020, 1, 1)
