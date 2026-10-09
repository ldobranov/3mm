"""Disposable Core DB/login tests; no live approval, service or external effect."""

import base64
import copy
from datetime import UTC, datetime, timedelta
import hashlib
import threading
import traceback

import backend.database  # noqa: F401
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import jwt
import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.application_policy_review import ApplicationPolicyReview as Review
from backend.db.application_policy_review import ApplicationPolicyReviewDecision as Decision
from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.db.session import UserSession
from backend.db.user import User
from backend.services import application_policy_reviews as service
from backend.services.authority_metadata import read_application_authority, read_authority_guard
from backend.tests.test_application_authority_policy import inputs
from backend.tests.test_application_authority_context import replace_path
from backend.utils import jwt_utils


CORE = "inst_" + "1" * 32


@pytest.fixture
def installed(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'reviews.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in (
        "users", "sessions", "core_authority_guard", "core_installation_identity", "module_packages",
        "application_extension_installations", "application_policy_reviews", "application_policy_review_decisions")])
    tokens = {uid: jwt_utils.create_access_token(str(uid), {"sid": uid, "token_version": 0,
        "token_type": "user", "role": "admin"}) for uid in (1, 2)}
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    with Session(engine) as db, db.begin():
        db.add(CoreAuthorityGuard(singleton_id=1, generation="2" * 32, revision=1))
        db.add(CoreInstallationIdentity(singleton_id=1, installation_id=CORE, identity_version=1,
            key_generation=1, key_id=hashlib.sha256(public).hexdigest(),
            public_key=base64.b64encode(public).decode(), encrypted_private_key="PRIVATE_IDENTITY_NEVER_READ",
            created_at=datetime.now(UTC)))
        for uid in (1, 2):
            db.add(User(id=uid, username=f"user{uid}", email=f"u{uid}@example.test",
                hashed_password="PRIVATE_PASSWORD_NEVER_READ", role="admin" if uid == 1 else "user"))
        db.add(ModulePackage(id=1, module_id="org.example.reference", version="1.0.0",
            manifest={}, sha256="a" * 64, size_bytes=1, file_path="unused"))
        db.flush()
        for uid in (1, 2):
            db.add(UserSession(id=uid, user_id=uid, token=tokens[uid], is_active=True,
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)))
        db.add(ApplicationExtensionInstallation(id=1, module_id="org.example.reference", module_package_id=1,
            active_version="1.0.0", instance_id="3" * 24, status="active", enabled=True,
            socket_path="unused", configuration={"password": "PRIVATE_CONFIGURATION"},
            authority_incarnation="3" * 32, authority_epoch="4" * 32))
    subject = inputs()[0]
    subject["binding"].update(recovery_generation="2" * 32)
    subject["binding"]["principal"].update(core_installation_id=CORE,
        application_installation_id="1", incarnation="3" * 32)
    subject["binding"]["baseline"].update(artifact={"version": "1.0.0", "sha256": "a" * 64},
        authority_epoch="4" * 32, enforcement_mode="compatibility")
    for connector in subject["connectors"]:
        connector["stored"]["owner"] = copy.deepcopy(subject["binding"]["principal"])
        connector["stored"]["credential"]["owner"] = copy.deepcopy(subject["binding"]["principal"])
    yield engine, subject, tokens
    engine.dispose()


def guard(engine):
    with Session(engine) as db:
        return read_authority_guard(db)


def state(engine):
    with Session(engine) as db:
        return (read_authority_guard(db), read_application_authority(db, 1),
            db.execute(select(*Review.__table__.c).order_by(Review.review_id)).all(),
            db.execute(select(*Decision.__table__.c).order_by(Decision.decision_id)).all())


def record(installed, *, subject=None, token=None, request="a" * 32, expected=None):
    engine, original, tokens = installed
    with Session(engine) as db:
        return service.record_policy_review(db, original if subject is None else subject,
            actor_token=tokens[1] if token is None else token, request_id=request,
            expected_guard=guard(engine) if expected is None else expected)


def decide(installed, review, decision, *, request="b" * 32, expected=None):
    engine, _subject, tokens = installed
    with Session(engine) as db:
        return service.decide_policy_review(db, review.review_id, decision=decision,
            actor_token=tokens[1], request_id=request, expected_revision=review.revision,
            expected_guard=guard(engine) if expected is None else expected)


def test_record_deny_revoke_are_atomic_audited_non_authorizing_and_keep_active_epoch(installed):
    engine, _subject, tokens = installed
    original = state(engine)
    first_guard = guard(engine)
    first = record(installed)
    assert first.decision == "recorded" and first.review.state == "review_required"
    assert not first.review.reviewable and first.review.permission_approval == "not_evaluated"
    assert first.review.recovery_binding_current
    recorded = state(engine)
    assert recorded[0].revision == original[0].revision + 1
    assert recorded[1] == original[1]
    denied = decide(installed, first.review, "denied")
    revoked = decide(installed, denied.review, "revoked", request="c" * 32)
    assert revoked.review.state == "revoked"
    final = state(engine)
    assert final[0].revision == original[0].revision + 3 and final[1] == original[1]
    assert final[2][0].subject_json == recorded[2][0].subject_json
    assert final[2][0].subject_sha256 == recorded[2][0].subject_sha256
    assert len(final[3]) == 3
    retry = record(installed, expected=first_guard)
    assert retry.replayed and retry.decision_revision == first.decision_revision
    assert retry.review == revoked.review  # Never hide the later revocation.
    assert state(engine) == final
    rendered = first.model_dump_json() + denied.model_dump_json() + revoked.model_dump_json()
    assert all(value not in rendered + repr(final[3]) for value in (
        tokens[1], "PRIVATE_CONFIGURATION", "PRIVATE_PASSWORD", "PRIVATE_IDENTITY", "api.example.test"))
    assert service.read_policy_review_status(engine, first.review.review_id) == revoked.review


@pytest.mark.parametrize("change", ["blocked", "demoted", "version", "session_revoked", "session_expired", "session_owner", "session_token"])
def test_current_actor_rechecked_even_for_exact_retry(installed, change):
    engine, _subject, _tokens = installed
    first_guard = guard(engine)
    record(installed)
    with Session(engine) as db, db.begin():
        if change == "blocked":
            db.execute(update(User).where(User.id == 1).values(is_blocked=True))
        elif change == "demoted":
            db.execute(update(User).where(User.id == 1).values(role="user"))
        elif change == "version":
            db.execute(update(User).where(User.id == 1).values(token_version=1))
        else:
            values = {"session_revoked": {"is_active": False},
                "session_expired": {"expires_at": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)},
                "session_owner": {"user_id": 2}, "session_token": {"token": "replacement"}}[change]
            db.execute(update(UserSession).where(UserSession.id == 1).values(**values))
    before = state(engine)
    with pytest.raises(service.PolicyReviewStoreError, match="actor_unavailable"):
        record(installed, expected=first_guard)
    assert state(engine) == before


@pytest.mark.parametrize("kind", ["user", "anonymous", "unsigned", "legacy", "device", "kiosk", "bool_sid", "expired", "no_exp"])
def test_claimed_role_id_or_service_token_is_not_admin_authority(installed, kind):
    engine, _subject, tokens = installed
    if kind == "user":
        token = tokens[2]  # Deliberately says role=admin; DB role is user.
    elif kind == "anonymous":
        token = ""
    elif kind == "unsigned":
        token = jwt.encode({"sub": "1"}, key="", algorithm="none")
    elif kind == "no_exp":
        token = jwt.encode({"sub": "1", "sid": 1, "token_version": 0}, jwt_utils.SECRET_KEY, algorithm=jwt_utils.ALGORITHM)
    else:
        claims = {"sid": 1, "token_version": 0}
        if kind == "legacy":
            claims.pop("sid")
        elif kind in {"device", "kiosk"}:
            claims["token_type"] = kind
        elif kind == "bool_sid":
            claims["sid"] = True
        token = jwt_utils.create_access_token("1", claims,
            expires_delta=timedelta(seconds=-30) if kind == "expired" else None)
    before = state(engine)
    with pytest.raises(service.PolicyReviewStoreError, match="actor_unavailable"):
        record(installed, token=token)
    assert state(engine) == before


@pytest.mark.parametrize("path,value", [
    (("principal", "core_installation_id"), "inst_" + "9" * 32),
    (("principal", "application_installation_id"), "99"),
    (("principal", "incarnation"), "9" * 32),
    (("principal", "module_id"), "org.example.other"),
    (("candidate", "sha256"), "9" * 64),
    (("candidate", "version"), "1.0.1"),
    (("baseline", "authority_epoch"), "9" * 32),
    (("baseline", "artifact", "sha256"), "9" * 64),
    (("baseline", "enforcement_mode"), "review_required"),
    (("recovery_generation",), "9" * 32),
])
def test_live_installation_and_exact_artifact_are_rechecked_under_guard(installed, path, value):
    engine, subject, _tokens = installed
    subject = copy.deepcopy(subject)
    replace_path(subject["binding"], path, value)
    before = state(engine)
    with pytest.raises(service.PolicyReviewStoreError):
        record(installed, subject=subject)
    assert state(engine) == before


def test_request_content_actor_or_operation_conflict_never_rewrites_history(installed):
    engine, subject, tokens = installed
    first = record(installed)
    with Session(engine) as db, db.begin():
        db.execute(update(User).where(User.id == 2).values(role="admin"))
    before = state(engine)
    changed = copy.deepcopy(subject)
    changed["binding"]["configuration"]["keyed_sha256"] = "9" * 64
    for token, value in ((tokens[1], changed), (tokens[2], subject)):
        with pytest.raises(service.PolicyReviewStoreError, match="request_conflict"):
            record(installed, token=token, subject=value)
    with pytest.raises(service.PolicyReviewStoreError, match="request_conflict"):
        decide(installed, first.review, "revoked", request="a" * 32)
    assert state(engine) == before


def test_recovery_keeps_history_but_cannot_rebind_old_subject_or_renew_retry(installed):
    engine, _subject, _tokens = installed
    first_guard = guard(engine)
    first = record(installed)
    with Session(engine) as db, db.begin():
        db.execute(update(CoreAuthorityGuard).values(generation="8" * 32, revision=2))
    historical = service.read_policy_review_status(engine, first.review.review_id)
    assert not historical.recovery_binding_current and not historical.reviewable
    retry = record(installed, expected=first_guard)
    assert retry.replayed and not retry.review.recovery_binding_current
    before = state(engine)
    with pytest.raises(service.PolicyReviewStoreError):
        record(installed, request="d" * 32)
    assert state(engine) == before
    # Explicit negative cleanup is allowed, but the stored original binding stays
    # old and no current executable policy is ever produced.
    revoked = decide(installed, historical, "revoked")
    assert not revoked.review.recovery_binding_current


def test_audit_failure_rolls_back_creation_or_negative_transition_and_guard(installed):
    engine, _subject, _tokens = installed

    def fail(*_args):
        raise RuntimeError("injected audit failure")

    for existing in (False, True):
        first = record(installed) if existing else None
        before = state(engine)
        event.listen(Decision, "before_insert", fail)
        try:
            with pytest.raises(RuntimeError, match="injected audit failure"):
                decide(installed, first.review, "revoked") if existing else record(installed)
        finally:
            event.remove(Decision, "before_insert", fail)
        assert state(engine) == before


@pytest.mark.parametrize("decision", ["approved", "active", "review_required", True, None])
def test_no_positive_decision_or_reopening_path_exists(installed, decision):
    engine, _subject, _tokens = installed
    first = record(installed)
    before = state(engine)
    with pytest.raises(service.PolicyReviewStoreError):
        decide(installed, first.review, decision)
    assert state(engine) == before
    with engine.begin() as db, pytest.raises(IntegrityError):
        db.execute(update(Review).values(state="approved"))


def test_revoked_is_terminal_and_same_request_is_idempotent(installed):
    engine, _subject, _tokens = installed
    first = record(installed)
    original_guard = guard(engine)
    last = decide(installed, first.review, "revoked")
    before = state(engine)
    assert decide(installed, first.review, "revoked", expected=original_guard).replayed
    with pytest.raises(service.PolicyReviewStoreError):
        decide(installed, last.review, "denied", request="c" * 32)
    with pytest.raises(service.PolicyReviewStoreError):
        decide(installed, last.review, "revoked", request="c" * 32)
    assert state(engine) == before


def test_deleting_application_and_human_session_does_not_delete_audit(installed):
    engine, _subject, _tokens = installed
    first = record(installed)
    with engine.begin() as db:
        db.execute(ApplicationExtensionInstallation.__table__.delete())
        db.execute(UserSession.__table__.delete())
        db.execute(User.__table__.delete())
    assert service.read_policy_review_status(engine, first.review.review_id).state == "review_required"
    with engine.connect() as db:
        assert db.scalar(select(Decision.actor_user_id)) == 1


@pytest.mark.parametrize("corrupt", ["payload", "hash", "head", "missing_audit", "missing_guard"])
def test_read_is_fail_closed_and_never_repairs_corrupt_state(installed, corrupt):
    engine, _subject, _tokens = installed
    first = record(installed)
    with engine.begin() as db:
        if corrupt == "payload":
            db.execute(update(Review).values(subject_json='{"PRIVATE":"not a subject"}'))
        elif corrupt == "hash":
            db.execute(update(Review).values(subject_sha256="0" * 64))
        elif corrupt == "head":
            db.execute(update(Review).values(revision="0" * 32))
        elif corrupt == "missing_audit":
            db.execute(Decision.__table__.delete())
        else:
            db.execute(CoreAuthorityGuard.__table__.delete())
    statements = []

    def capture(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        with pytest.raises(service.PolicyReviewStoreError) as error:
            service.read_policy_review_status(engine, first.review.review_id)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any(s.lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for s in statements)
    assert "PRIVATE" not in "".join(traceback.format_exception(error.value))


def test_clean_scope_required_and_guard_is_the_first_write(installed):
    engine, subject, tokens = installed
    with Session(engine) as db:
        actor = db.get(User, 1)
        actor.username = "pending-only"
        with pytest.raises(service.PolicyReviewStoreError):
            service.record_policy_review(db, subject, actor_token=tokens[1], request_id="a" * 32,
                expected_guard=guard(engine))
        assert actor in db.dirty and actor.username == "pending-only"
    writes = []

    def capture(_conn, _cursor, statement, *_args):
        if statement.lstrip().startswith(("UPDATE", "INSERT", "DELETE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        record(installed)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert writes[0].startswith("UPDATE core_authority_guard")
    assert "users" in writes[1] and "sessions" in writes[2]


def test_real_two_connection_duplicate_record_commits_only_one_review_and_audit(installed, monkeypatch):
    engine, _subject, _tokens = installed
    expected = guard(engine)
    attempted, done = threading.Event(), threading.Event()
    results = []
    original = service._append

    def run():
        try:
            results.append(record(installed, expected=expected))
        except BaseException as exc:
            results.append(exc)
        finally:
            done.set()

    second = threading.Thread(target=run, name="second-policy-writer")

    def capture(_conn, _cursor, statement, *_args):
        if threading.current_thread() is second and statement.startswith("UPDATE core_authority_guard"):
            attempted.set()

    def append(*args, **kwargs):
        if threading.current_thread() is not second:
            second.start()
            assert attempted.wait(2) and not done.wait(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "_append", append)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        results.append(record(installed, expected=expected))
        assert done.wait(6)
    finally:
        if second.ident is not None:
            second.join(6)
        event.remove(engine, "before_cursor_execute", capture)
    assert all(isinstance(value, service.PolicyReviewReceipt) for value in results), results
    assert sorted(value.replayed for value in results) == [False, True]
    assert len({value.review.review_id for value in results}) == 1
    current = state(engine)
    assert len(current[2]) == len(current[3]) == 1 and current[0].revision == expected.revision + 1


def test_real_competing_negative_decisions_have_one_winner(installed):
    engine, _subject, _tokens = installed
    first = record(installed)
    expected = guard(engine)
    barrier, results = threading.Barrier(3), []

    def run(decision, request):
        barrier.wait(timeout=3)
        try:
            results.append(decide(installed, first.review, decision, request=request, expected=expected))
        except service.PolicyReviewStoreError:
            results.append("stale")

    threads = [threading.Thread(target=run, args=(decision, request))
        for decision, request in (("denied", "b" * 32), ("revoked", "c" * 32))]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(6)
        assert not thread.is_alive()
    assert sum(isinstance(value, service.PolicyReviewReceipt) for value in results) == 1
    assert results.count("stale") == 1
    assert len(state(engine)[3]) == 2 and guard(engine).revision == expected.revision + 1
