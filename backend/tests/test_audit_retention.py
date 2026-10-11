"""Bounded audit-log retention (M15): age-based purge preserves evidence."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.audit_log import AuditLog
from backend.db.base import Base
from backend.db.user import User
from backend.routes import audit_routes
from backend.routes.audit_routes import router
from backend.services import audit_retention
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token


@pytest.fixture(autouse=True)
def use_test_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "test-only-key-with-at-least-32-bytes")


def make_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def add_log(db, *, action, entity_type=None, entity_name=None, timestamp):
    db.add(
        AuditLog(
            user_id=1,
            action=action,
            entity_type=entity_type,
            entity_name=entity_name,
            timestamp=timestamp,
        )
    )


def test_retention_plan_counts_only_old_non_evidential_rows():
    engine = make_engine()
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2026, 1, 1)
    old = now - timedelta(days=120)
    fresh = now - timedelta(days=10)

    add_log(db, action="LOGIN", timestamp=old)  # old, evictable
    add_log(db, action="LOGIN", timestamp=old)  # old, evictable
    add_log(db, action="LOGIN", timestamp=fresh)  # fresh, keep
    add_log(
        db,
        action="NODE_UPDATE_EXECUTION_UNCONFIRMED",
        entity_type="device_node_update",
        timestamp=old,
    )  # old, evidential
    add_log(
        db,
        action="APPLICATION_ACTIVATION_ROLLBACK",
        entity_type="application_extension",
        timestamp=old,
    )  # old, evidential
    db.commit()

    plan = audit_retention.plan_audit_retention(db, now=now, retention_days=90)
    assert plan.candidate_total == 2
    assert plan.protected_evidential == 2
    db.close()


def test_apply_retention_deletes_only_old_non_evidential_rows():
    engine = make_engine()
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2026, 1, 1)
    old = now - timedelta(days=120)
    add_log(db, action="LOGIN", timestamp=old)
    add_log(db, action="LOGIN", timestamp=old)
    add_log(
        db,
        action="NODE_UPDATE_EXECUTION_UNCONFIRMED",
        entity_type="device_node_update",
        timestamp=old,
    )
    db.commit()

    deleted = audit_retention.apply_audit_retention(
        db, now=now, retention_days=90, max_batch=100
    )
    db.commit()
    assert deleted == 2
    remaining = db.execute(select(AuditLog)).scalars().all()
    assert [row.action for row in remaining] == ["NODE_UPDATE_EXECUTION_UNCONFIRMED"]
    db.close()


def test_apply_retention_respects_max_batch():
    engine = make_engine()
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2026, 1, 1)
    old = now - timedelta(days=120)
    for _ in range(5):
        add_log(db, action="LOGIN", timestamp=old)
    db.commit()

    deleted = audit_retention.apply_audit_retention(
        db, now=now, retention_days=90, max_batch=2
    )
    db.commit()
    assert deleted == 2
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 3
    db.close()


def test_apply_retention_is_memory_bounded_with_large_journal():
    """128 old rows + max_batch=1 must not load the whole journal to delete one."""
    from sqlalchemy import event

    engine = make_engine()
    Base.metadata.create_all(engine)
    db = Session(engine)
    now = datetime(2026, 1, 1)
    old = now - timedelta(days=120)
    for _ in range(128):
        add_log(db, action="LOGIN", timestamp=old)
    db.commit()

    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        deleted = audit_retention.apply_audit_retention(
            db, now=now, retention_days=90, max_batch=1
        )
        db.commit()
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert deleted == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 127
    # The candidate selection must be bounded by SQL LIMIT, not a full scan.
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert any("LIMIT" in s.upper() for s in selects), statements
    db.close()


@pytest.mark.parametrize("days", [0, 29, 3651, True])
def test_retention_rejects_out_of_range_days(days):
    engine = make_engine()
    Base.metadata.create_all(engine)
    db = Session(engine)
    with pytest.raises(audit_retention.AuditRetentionError):
        audit_retention.retention_cutoff(datetime.utcnow(), days)
    db.close()


def test_retention_normalizes_aware_cutoff_to_utc():
    now = datetime(2026, 1, 1, 3, tzinfo=timezone(timedelta(hours=3)))
    assert audit_retention.retention_cutoff(now, 90) == (
        datetime(2026, 1, 1) - timedelta(days=90)
    )


@pytest.mark.parametrize("field", ["action", "entity_type", "entity_name"])
def test_retention_protects_case_insensitive_evidence_and_cutoff_boundary(field):
    engine = make_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime(2026, 1, 1)
        cutoff = now - timedelta(days=90)
        values = {"action": "LOGIN", field: "pending_review"}
        add_log(db, **values, timestamp=cutoff - timedelta(days=1))
        add_log(db, action="LOGIN", timestamp=cutoff)
        add_log(db, action="LOGIN", timestamp=cutoff - timedelta(days=1))
        db.commit()
        plan = audit_retention.plan_audit_retention(db, now=now, retention_days=90)
        assert (plan.candidate_total, plan.protected_evidential) == (1, 1)
        assert (
            audit_retention.apply_audit_retention(
                db, now=now, retention_days=90, max_batch=100
            )
            == 1
        )
        db.rollback()
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 3


def make_client(tmp_path):
    engine = make_engine()
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
    db.flush()
    db.add(
        AuditLog(
            user_id=1,
            action="LOGIN",
            timestamp=datetime.utcnow() - timedelta(days=120),
        )
    )
    db.commit()
    admin_token = create_access_token(str(admin.id), {"role": "admin"})
    viewer_token = create_access_token(str(viewer.id), {"role": "user"})
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db, admin_token, viewer_token


def test_retention_endpoints_are_admin_only_and_require_confirmation(tmp_path):
    client, db, admin_token, viewer_token = make_client(tmp_path)
    try:
        assert client.get("/api/audit-logs/retention-plan").status_code == 401
        assert (
            client.get(
                "/api/audit-logs/retention-plan",
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )
        payload = {"retention_days": 90, "confirmation": "AUDIT RETENTION"}
        assert client.post("/api/audit-logs/retention", json=payload).status_code == 401
        assert (
            client.post(
                "/api/audit-logs/retention",
                json=payload,
                headers={"Authorization": f"Bearer {viewer_token}"},
            ).status_code
            == 403
        )
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1

        plan = client.get(
            "/api/audit-logs/retention-plan",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert plan.status_code == 200
        assert plan.json()["candidate_total"] == 1

        wrong = client.post(
            "/api/audit-logs/retention",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"retention_days": 90, "confirmation": "no"},
        )
        assert wrong.status_code == 409

        applied = client.post(
            "/api/audit-logs/retention",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "retention_days": 90,
                "confirmation": "AUDIT RETENTION",
                "max_batch": 1000,
            },
        )
        assert applied.status_code == 200
        assert applied.json() == {"deleted": 1}
        # The retention action itself is audited.
        actions = [
            row.action
            for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars()
        ]
        assert actions == ["AUDIT_RETENTION_APPLIED"]
    finally:
        db.close()
