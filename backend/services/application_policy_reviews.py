"""Core-private, non-authorizing review history. No public API or positive grant.

Subjects are pending review snapshots, NOT verified native provenance/evidence.
Even their configuration/resource claims must be re-resolved before any future
approval. This store cannot return CorePolicyEvidenceV1 or activate anything.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.application_policy_review import ApplicationPolicyReview as Review
from backend.db.application_policy_review import ApplicationPolicyReviewDecision as Decision
from backend.db.session import UserSession
from backend.db.user import User
from backend.services.application_authority_context import ContextModel, _canonical_bytes, _parse
from backend.services.application_authority_policy import PolicySubjectV1, _scope_data
from backend.services.application_authority_sources import _core_identity, _package_pin, _read_snapshot
from backend.services.authority_metadata import (
    AuthorityGuardSnapshot, AuthorityMetadataError, authority_transaction,
    read_application_authority, read_authority_guard,
)
from backend.db.authority import MAX_AUTHORITY_REVISION, new_authority_generation
from backend.utils.jwt_utils import decode_token


SUBJECT_DOMAIN = b"3mm:m20:policy-review-subject:v1\x00"
REQUEST_DOMAIN = b"3mm:m20:policy-review-request:v1\x00"
SESSION_DOMAIN = b"3mm:m20:policy-review-actor-session:v1\x00"
State = Literal["review_required", "denied", "revoked"]


class PolicyReviewStoreError(ValueError):
    def __init__(self, reason="review_unavailable"):
        # Call sites use fixed codes only. Never wrap raw SQL, tokens or subjects.
        self.reason = reason
        super().__init__("Policy review is unavailable: " + reason)


class PolicyReviewStatus(ContextModel):
    review_id: str
    revision: str
    state: State
    recovery_binding_current: bool
    reviewable: Literal[False] = False
    permission_approval: Literal["not_evaluated"] = "not_evaluated"


class PolicyReviewReceipt(ContextModel):
    review: PolicyReviewStatus
    decision: Literal["recorded", "denied", "revoked"]
    decision_revision: str
    replayed: bool


def _id(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise PolicyReviewStoreError("invalid_request")
    return value


def _guard(value):
    if (not isinstance(value, AuthorityGuardSnapshot) or type(value.revision) is not int
            or not 1 <= value.revision < MAX_AUTHORITY_REVISION):
        raise PolicyReviewStoreError("invalid_request")
    _id(value.generation)
    return value


def _subject(value):
    subject = _parse(PolicySubjectV1, value)
    data = subject.model_dump(mode="json")
    data["commands"] = [_scope_data(scope) for scope in sorted(
        subject.commands, key=lambda scope: scope.declaration.binding_id)]
    data["connectors"] = [_scope_data(scope) for scope in sorted(
        subject.connectors, key=lambda scope: scope.declaration.connector_id)]
    data["blockers"].sort()
    encoded = json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(SUBJECT_DOMAIN + _canonical_bytes(data)).hexdigest()
    return subject, encoded, digest


def _actor(db, token):
    """Verify a real signed login and lock/recheck its current account/session.

    Strict new-write boundary only: no legacy sessionless token, claimed role,
    application/device/kiosk token or caller-supplied user ID. Global login APIs
    and compatibility sessions are not changed.
    """
    if type(token) is not str or not 1 <= len(token) <= 4096:
        raise PolicyReviewStoreError("actor_unavailable")
    try:
        claims = decode_token(token)
        now = datetime.now(UTC)
        uid, sid, version, expiry = (claims.get(key) for key in ("sub", "sid", "token_version", "exp"))
        if (type(uid) is not str or re.fullmatch(r"[1-9][0-9]{0,15}", uid) is None
                or type(sid) is not int or sid < 1 or type(version) is not int or version < 0
                or type(expiry) is not int or expiry <= now.timestamp()
                or claims.get("token_type", "user") != "user"):
            raise PolicyReviewStoreError("actor_unavailable")
        uid = int(uid)
        # Guard -> user -> session -> application -> review. Fresh SQL predicates
        # also serialize against blocking/demotion/session-revocation writers.
        if db.execute(update(User).where(User.id == uid, User.role == "admin",
                User.is_blocked.is_(False), User.token_version == version)
                .values(token_version=User.token_version)
                .execution_options(synchronize_session=False)).rowcount != 1:
            raise PolicyReviewStoreError("actor_unavailable")
        if db.execute(update(UserSession).where(UserSession.id == sid, UserSession.user_id == uid,
                UserSession.is_active.is_(True), UserSession.token == token,
                UserSession.expires_at > now.replace(tzinfo=None))
                .values(is_active=UserSession.is_active)
                .execution_options(synchronize_session=False)).rowcount != 1:
            raise PolicyReviewStoreError("actor_unavailable")
        return uid, sid, hashlib.sha256(SESSION_DOMAIN + token.encode("utf-8")).hexdigest()
    except HTTPException:
        raise PolicyReviewStoreError("actor_unavailable") from None


def _row(db, review_id):
    row = db.execute(select(*Review.__table__.c).where(Review.review_id == review_id)).one_or_none()
    if row is None:
        raise PolicyReviewStoreError()
    subject, _encoded, digest = _subject(row.subject_json)
    binding = subject.binding
    if (digest != row.subject_sha256 or row.core_installation_id != binding.principal.core_installation_id
            or row.recovery_generation != binding.recovery_generation
            or str(row.application_installation_id) != binding.principal.application_installation_id
            or row.incarnation != binding.principal.incarnation or row.module_id != binding.principal.module_id
            or row.artifact_sha256 != binding.candidate.sha256):
        raise PolicyReviewStoreError()
    # There are at most recorded -> denied -> revoked. Validate the bounded audit
    # chain/head, not only mutable state or timestamps (which can tie/roll back).
    events = db.execute(select(*Decision.__table__.c).where(Decision.review_id == review_id).limit(4)).all()
    if not 1 <= len(events) <= 3:
        raise PolicyReviewStoreError()
    by_previous = {event.previous_revision: event for event in events}
    if len(by_previous) != len(events) or None not in by_previous:
        raise PolicyReviewStoreError()
    previous, state, count = None, None, 0
    while previous in by_previous:
        event = by_previous[previous]
        _id(event.revision)
        permitted = {None: {"recorded"}, "review_required": {"denied", "revoked"}, "denied": {"revoked"}, "revoked": set()}
        if event.decision not in permitted[state] or event.reason != {
                "recorded": "review_required", "denied": "operator_denied", "revoked": "operator_revoked"}.get(event.decision):
            raise PolicyReviewStoreError()
        state = "review_required" if event.decision == "recorded" else event.decision
        previous, count = event.revision, count + 1
        if count > 3:
            raise PolicyReviewStoreError()
    if count != len(events) or (previous, state) != (row.revision, row.state):
        raise PolicyReviewStoreError()
    return row


def _status(row, core_id, guard):
    return PolicyReviewStatus(review_id=row.review_id, revision=row.revision, state=row.state,
        recovery_binding_current=(row.core_installation_id == core_id and row.recovery_generation == guard.generation))


def _receipt(db, event, core_id, guard, *, replayed):
    return PolicyReviewReceipt(review=_status(_row(db, event.review_id), core_id, guard),
        decision=event.decision, decision_revision=event.revision, replayed=replayed)


def _retry(db, request_id, digest, actor, core_id, guard):
    event = db.execute(select(*Decision.__table__.c).where(Decision.request_id == request_id)).one_or_none()
    if event is None:
        return None
    row = _row(db, event.review_id)
    if (event.request_sha256 != digest
            or (event.actor_user_id, event.actor_session_id, event.actor_session_sha256) != actor
            or row.core_installation_id != core_id):
        raise PolicyReviewStoreError("request_conflict")
    # Historical receipt, never refresh/rebind the original review or hide a
    # later deny/revoke. Current actor is still mandatory on EVERY retry.
    return _receipt(db, event, core_id, guard, replayed=True)


def _bind_installed_subject(db, subject, core_id, authority):
    binding, principal = subject.binding, subject.binding.principal
    identifier = principal.application_installation_id
    if re.fullmatch(r"[1-9][0-9]{0,15}", identifier) is None:
        raise PolicyReviewStoreError("stale_subject")
    current = read_application_authority(db, int(identifier))
    authority.lock_application(current)
    pin = _package_pin(db, current.installation_id)
    baseline = binding.baseline
    if (principal.core_installation_id != core_id or binding.recovery_generation != authority.guard.generation
            or (principal.module_id, principal.incarnation, baseline.authority_epoch, baseline.enforcement_mode)
                != (current.module_id, current.incarnation, current.epoch, current.mode)
            or baseline.grant_revision is not None or baseline.artifact is None
            or (baseline.artifact.version, baseline.artifact.sha256) != (pin.version, pin.sha256)
            or (binding.candidate.version, binding.candidate.sha256) != (pin.version, pin.sha256)):
        raise PolicyReviewStoreError("stale_subject")
    return current.installation_id


def _append(db, row, *, request_id, request_digest, actor, generation, previous, revision, decision):
    event = Decision(decision_id=new_authority_generation(), review_id=row.review_id,
        request_id=request_id, request_sha256=request_digest,
        actor_user_id=actor[0], actor_session_id=actor[1], actor_session_sha256=actor[2],
        recovery_generation=generation, previous_revision=previous, revision=revision,
        decision=decision, reason={"recorded": "review_required", "denied": "operator_denied", "revoked": "operator_revoked"}[decision])
    db.add(event)
    db.flush()  # Audit failure rolls back the head, guard and entire operation.
    return event


def record_policy_review(db: Session, subject, *, actor_token: str, request_id: str,
        expected_guard: AuthorityGuardSnapshot) -> PolicyReviewReceipt:
    """Record a pending installed-only snapshot, not a staged candidate/grant.

    Caller is trusted Core coordination, not package/browser input. The store
    rechecks live installation/artifact ownership, but does NOT authenticate the
    supplied configuration/resource/proof claims. These remain unverified.
    """
    try:
        request_id, expected_guard = _id(request_id), _guard(expected_guard)
        subject, encoded, subject_digest = _subject(subject)
        request_digest = hashlib.sha256(REQUEST_DOMAIN + _canonical_bytes({
            "operation": "recorded", "subject_sha256": subject_digest})).hexdigest()
        with authority_transaction(db) as authority:
            actor, core_id = _actor(db, actor_token), _core_identity(db)
            replay = _retry(db, request_id, request_digest, actor, core_id, authority.guard)
            if replay is not None:
                return replay
            if authority.guard != expected_guard:
                authority.reject()
            installation_id = _bind_installed_subject(db, subject, core_id, authority)
            revision = new_authority_generation()
            row = Review(review_id=new_authority_generation(), core_installation_id=core_id,
                recovery_generation=authority.guard.generation, application_installation_id=installation_id,
                incarnation=subject.binding.principal.incarnation, module_id=subject.binding.principal.module_id,
                artifact_sha256=subject.binding.candidate.sha256, subject_json=encoded,
                subject_sha256=subject_digest, state="review_required", revision=revision)
            db.add(row)
            db.flush()
            event = _append(db, row, request_id=request_id, request_digest=request_digest,
                actor=actor, generation=authority.guard.generation, previous=None,
                revision=revision, decision="recorded")
            authority.advance_guard_revision()
            return _receipt(db, event, core_id, authority.guard, replayed=False)
    except PolicyReviewStoreError:
        raise
    except (SQLAlchemyError, AuthorityMetadataError, ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        raise PolicyReviewStoreError() from None


def decide_policy_review(db: Session, review_id: str, *, decision: Literal["denied", "revoked"],
        actor_token: str, request_id: str, expected_revision: str,
        expected_guard: AuthorityGuardSnapshot) -> PolicyReviewReceipt:
    """Append a negative decision only. Cannot approve, reopen, grant or activate."""
    try:
        review_id, request_id, expected_revision = _id(review_id), _id(request_id), _id(expected_revision)
        expected_guard = _guard(expected_guard)
        if type(decision) is not str or decision not in {"denied", "revoked"}:
            raise PolicyReviewStoreError("invalid_request")
        request_digest = hashlib.sha256(REQUEST_DOMAIN + _canonical_bytes({
            "operation": decision, "review_id": review_id, "previous_revision": expected_revision})).hexdigest()
        with authority_transaction(db) as authority:
            actor, core_id = _actor(db, actor_token), _core_identity(db)
            replay = _retry(db, request_id, request_digest, actor, core_id, authority.guard)
            if replay is not None:
                return replay
            if authority.guard != expected_guard:
                authority.reject()
            row = _row(db, review_id)
            if (row.core_installation_id != core_id or row.revision != expected_revision
                    or row.state == "revoked" or (decision == "denied" and row.state != "review_required")):
                raise PolicyReviewStoreError("stale_subject")
            revision = new_authority_generation()
            changed = db.execute(update(Review).where(Review.review_id == review_id,
                Review.revision == expected_revision, Review.state == row.state)
                .values(state=decision, revision=revision).execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                authority.reject()
            event = _append(db, row, request_id=request_id, request_digest=request_digest,
                actor=actor, generation=authority.guard.generation, previous=expected_revision,
                revision=revision, decision=decision)
            authority.advance_guard_revision()
            return _receipt(db, event, core_id, authority.guard, replayed=False)
    except PolicyReviewStoreError:
        raise
    except (SQLAlchemyError, AuthorityMetadataError, ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        raise PolicyReviewStoreError() from None


def read_policy_review_status(engine, review_id: str) -> PolicyReviewStatus:
    """Internal Core reader, not an unauthenticated HTTP/history endpoint.

    Genuine read-only snapshot; no lazy state/key creation, raw payload, secret
    values or executable policy are returned. Recovery-current is ONLY the Core/
    recovery binding check, not live artifact/resource/configuration freshness.
    """
    try:
        review_id = _id(review_id)
        with _read_snapshot(engine) as db:
            return _status(_row(db, review_id), _core_identity(db), read_authority_guard(db))
    except PolicyReviewStoreError:
        raise
    except (SQLAlchemyError, ValueError, TypeError, AttributeError, RecursionError, OverflowError):
        raise PolicyReviewStoreError() from None
