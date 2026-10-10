"""Installed-artifact, reviewed-native authority coordinator.

The native review writer is LOCAL CORE ADMINISTRATION ONLY, not an HTTP/SDK
checkbox. It records an authenticated human code-review attestation, never an
OS/browser isolation proof. No staged artifact, unsupported scope or UI bypass.
"""

from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import time

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import (
    ApplicationNativeReview as Native, ApplicationAuthorityPlan as Plan,
    ApplicationAuthorityGrant as Grant, ApplicationAuthorityAction as Action,
)
from backend.db.audit_log import AuditLog
from backend.db.authority import CoreAuthorityGuard, new_authority_generation
from backend.db.module import ApplicationExtensionInstallation
from backend.services.application_authority_context import (
    AuthorityReviewContextV1, AuthorityReviewContextV2, AuthoritySelectionV1, AuthoritySelectionV2,
    AuthorityReviewContextV3, AuthoritySelectionV3,
    AuthorityReviewContextV4, AuthoritySelectionV4,
    AuthorityReviewContextV5, AuthoritySelectionV5,
    _bounded_json, _canonical_bytes, _parse, _parse_versioned, review_authority_context,
)
from backend.services.application_authority_keys import CoreReviewKeyStore, AuthorityReviewKeyError
from backend.services.application_authority_policy import (
    CorePolicyEvidenceV1, CorePolicyEvidenceV2, PolicySubjectV1, PolicySubjectV2,
    CorePolicyEvidenceV3, PolicySubjectV3,
    CorePolicyEvidenceV4, PolicySubjectV4,
    CorePolicyEvidenceV5, PolicySubjectV5,
    evaluate_authority_policy, _scopes,
)
from backend.services.application_authority_sources import _prepare_installed_package, _read_snapshot
from backend.services.application_authority_subjects import _compose
from backend.services.application_policy_reviews import _actor, PolicyReviewStoreError
from backend.services.authority_metadata import authority_transaction, read_application_authority


class AuthorityManagementError(Exception):
    def __init__(self, reason="authority_unavailable"):
        self.reason = reason
        super().__init__("Application authority unavailable: " + reason)


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise AuthorityManagementError("invalid_request")
    return value


def _digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AuthorityManagementError("invalid_request")
    return value


def _clock():
    # Linux boot time includes suspend; reboot never renews an old review.
    if os.name != "posix" or not hasattr(time, "CLOCK_BOOTTIME"):
        raise AuthorityManagementError("review_clock_unavailable")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f-]{36}", boot):
        raise AuthorityManagementError("review_clock_unavailable")
    return boot, time.clock_gettime_ns(time.CLOCK_BOOTTIME) // 1_000_000


def _save(db, key, kind, row, data):
    value = _bounded_json(data)
    row.payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    row.key_id, row.seal = key.seal(db, kind, value)
    db.add(row)
    db.flush()
    return value


def _load(db, key, kind, row, record_id):
    if row is None:
        raise AuthorityManagementError("record_unavailable")
    # Reuse strict duplicate-key/size handling before authenticating stored JSON.
    from backend.services.application_authority_context import _unique_object
    if type(row.payload) is not str or len(row.payload) > 131072:
        raise AuthorityManagementError("record_unavailable")
    value = _bounded_json(json.loads(row.payload, object_pairs_hook=_unique_object))
    key.verify(db, kind, value, row.key_id, row.seal)
    if (set(value) != {"version", "kind", "record_id", "installation_id", "revision", "state", "data"}
            or type(value["version"]) is not int or value["version"] != 1 or value["kind"] != kind
            or value["record_id"] != str(record_id) or value["installation_id"] != row.installation_id):
        raise AuthorityManagementError("record_unavailable")
    _identifier(value["revision"])
    return value


def _envelope(kind, record_id, installation_id, state, data):
    return {"version": 1, "kind": kind, "record_id": str(record_id),
        "installation_id": installation_id, "revision": new_authority_generation(), "state": state, "data": data}


def _native_binding(subject):
    binding = subject.binding
    return {"principal": binding.principal.model_dump(mode="json"),
        "artifact": binding.candidate.model_dump(mode="json"), "recovery_generation": binding.recovery_generation}


def _resource_identity(subject):
    value = subject.model_dump(mode="json")
    # Active grant records the reviewed OLD baseline and a separate resulting
    # epoch/revision. Never rewrite the approved review context to fake freshness.
    value["binding"].pop("baseline")
    return _canonical_bytes(value)


def _resources(subject):
    return {name: getattr(subject, name) for name in ("commands", "connectors", "events", "publications", "private_files", "relational")
        if hasattr(subject, name)}


def _subject_scopes(subject):
    return _scopes(**_resources(subject))


class ApplicationAuthorityManager:
    def __init__(self, engine, *, uploads_root, core_version, review_key_directory):
        self.engine, self.uploads_root, self.core_version = engine, Path(uploads_root), core_version
        self.keys = CoreReviewKeyStore(engine, Path(review_key_directory))

    def _prepare(self, installation_id):
        try:
            return _prepare_installed_package(self.engine, installation_id, self.uploads_root, self.core_version)
        except (SQLAlchemyError, ValueError, OSError):
            raise AuthorityManagementError('artifact_unavailable') from None

    def _subject(self, db, key, installation_id, prepared):
        result = _compose(db, installation_id, *prepared, key)
        if result.subject is None or result.subject.blockers or result.subject.has_executable_frontend:
            raise AuthorityManagementError("unsupported_authority")
        return result.subject

    def _policy(self, db, key, subject, native_id):
        native = _load(db, key, "native", db.get(Native, _identifier(native_id), populate_existing=True), native_id)
        if (native["state"] != "reviewed_native" or native["installation_id"] != int(subject.binding.principal.application_installation_id)
                or _canonical_bytes(native["data"]["binding"]) != _canonical_bytes(_native_binding(subject))):
            raise AuthorityManagementError("native_review_unavailable")
        scopes = tuple(sorted(_subject_scopes(subject)))
        model = {1: CorePolicyEvidenceV1, 2: CorePolicyEvidenceV2, 3: CorePolicyEvidenceV3, 4: CorePolicyEvidenceV4, 5: CorePolicyEvidenceV5}[subject.subject_version]
        evidence = model(evidence_version=subject.subject_version, binding=subject.binding,
            policy_revision=native["revision"], trust_revision=native["revision"],
            trust_class="reviewed_local_artifact", execution_class="reviewed_native",
            execution_profile="supervised_reviewed_native_v1", profile_revision="1",
            native_review_revision=native["revision"], isolation_proof_revision=None,
            required_scopes=scopes, **_resources(subject))
        result = evaluate_authority_policy(subject, evidence)
        if not result.policy_resolved:
            raise AuthorityManagementError("policy_unavailable")
        return native, result.policy

    @contextmanager
    def _write(self, installation_id, actor_token, request_id, operation, request):
        request_id = _identifier(request_id)
        request_hash = hashlib.sha256(b"3mm:m20:authority-request:v1\x00" + _canonical_bytes({
            "installation_id": installation_id, "operation": operation, "request": request})).hexdigest()
        try:
            # Lock order: key -> DB guard -> current actor -> application. Hold
            # through commit, never through network/helper/artifact validation.
            with self.keys.locked() as key, Session(self.engine) as db, authority_transaction(db) as mutation:
                try:
                    actor = list(_actor(db, actor_token))
                except PolicyReviewStoreError:
                    raise AuthorityManagementError("actor_unavailable") from None
                existing = db.get(Action, request_id)
                if existing is not None:
                    receipt = _load(db, key, "action", existing, request_id)
                    if (receipt["installation_id"] != installation_id or receipt["data"]["request_hash"] != request_hash
                            or receipt["data"]["actor"] != actor):
                        raise AuthorityManagementError("request_conflict")
                    yield db, key, mutation, actor, {**receipt["data"]["result"], "replayed": True, "historical": True}
                    return
                current = read_application_authority(db, installation_id)
                mutation.lock_application(current)
                result = {}
                yield db, key, mutation, actor, result
                data = {"request_hash": request_hash, "actor": actor, "operation": operation, "result": result}
                _save(db, key, "action", Action(request_id=request_id, installation_id=installation_id),
                    _envelope("action", request_id, installation_id, "recorded", data))
                db.add(AuditLog(user_id=actor[0], action="APPLICATION_AUTHORITY_" + operation.upper(),
                    entity_type="application_extension", entity_name=current.module_id,
                    changes={"request_id": request_id, **result}))
                db.flush()
                mutation.advance_guard_revision()
        except AuthorityManagementError:
            raise
        except (AuthorityReviewKeyError, SQLAlchemyError, ValueError, TypeError, KeyError, AttributeError, OSError):
            raise AuthorityManagementError() from None

    def record_native_review(self, installation_id, *, actor_token, request_id, artifact_sha256,
            review_document_sha256, native_code_review_completed, accepts_native_host_risk):
        """LOCAL administrative code-review attestation; deliberately NO HTTP route.

        The operator actually reviews the exact code and supplies its review
        document digest. This is explicit native trust, NOT verified isolation or
        publisher ownership, and cannot approve any permission plan by itself.
        """
        if native_code_review_completed is not True or accepts_native_host_risk is not True:
            raise AuthorityManagementError("native_review_required")
        request = {"artifact_sha256": _digest(artifact_sha256), "review_document_sha256": _digest(review_document_sha256)}
        prepared = self._prepare(installation_id)
        with self._write(installation_id, actor_token, request_id, "native_review", request) as (db, key, mutation, actor, result):
            if result:
                return result
            subject = self._subject(db, key, installation_id, prepared)
            if subject.binding.candidate.sha256 != artifact_sha256:
                raise AuthorityManagementError("artifact_changed")
            identifier = new_authority_generation()
            value = _envelope("native", identifier, installation_id, "reviewed_native", {
                "binding": _native_binding(subject), "actor": actor, **request,
                "review_kind": "authenticated_local_manual_code_review", "isolation_proven": False})
            _save(db, key, "native", Native(review_id=identifier, installation_id=installation_id), value)
            result.update(native_review_id=identifier, native_revision=value["revision"], permission_approval="not_evaluated")
        return result

    def create_review(self, installation_id, *, actor_token, request_id, native_review_id, scopes):
        # Validate bounded identifiers before storage; the Core-resolved subject
        # selects the internal version, never an HTTP caller's version hint.
        requested = _parse(AuthoritySelectionV5, {"selection_version": 5, "scopes": scopes})
        request_version = 5 if any(scope.startswith('storage:relational_') for scope in requested.scopes) else 4 if any(scope.startswith('storage:') for scope in requested.scopes) else 3 if any(scope.startswith('publication:') for scope in requested.scopes) else (
            2 if any(scope.startswith('event:') for scope in requested.scopes) else 1)
        request_selection = _parse({1: AuthoritySelectionV1, 2: AuthoritySelectionV2, 3: AuthoritySelectionV3, 4: AuthoritySelectionV4, 5: AuthoritySelectionV5}[request_version],
            {'selection_version': request_version, 'scopes': scopes})
        request = {"native_review_id": _identifier(native_review_id), "selection": request_selection.model_dump(mode="json")}
        prepared = self._prepare(installation_id)
        with self._write(installation_id, actor_token, request_id, "review", request) as (db, key, mutation, actor, result):
            if result:
                return result
            subject = self._subject(db, key, installation_id, prepared)
            selection_model = {1: AuthoritySelectionV1, 2: AuthoritySelectionV2, 3: AuthoritySelectionV3, 4: AuthoritySelectionV4, 5: AuthoritySelectionV5}[subject.subject_version]
            selection = _parse(selection_model, {'selection_version': subject.subject_version, 'scopes': scopes})
            native, policy = self._policy(db, key, subject, native_review_id)
            boot, now = _clock()
            context_model = {1: AuthorityReviewContextV1, 2: AuthorityReviewContextV2, 3: AuthorityReviewContextV3, 4: AuthorityReviewContextV4, 5: AuthorityReviewContextV5}[subject.subject_version]
            context = context_model(context_version=subject.subject_version, **subject.binding.model_dump(exclude={"recovery_generation"}),
                policy=policy, issued_at_ms=now, expires_at_ms=now + 900_000, **_resources(subject))
            context = _parse(context_model, context)
            review = review_authority_context(context, selection, now_ms=now)
            if not review.reviewable:
                raise AuthorityManagementError("selection_not_allowed")
            identifier = new_authority_generation()
            value = _envelope("plan", identifier, installation_id, "review_required", {
                "subject": subject.model_dump(mode="json"), "context": context.model_dump(mode="json"),
                "selection": selection.model_dump(mode="json"), "fingerprint": review.context_fingerprint,
                "native_review_id": native_review_id, "native_revision": native["revision"], "boot_id": boot})
            _save(db, key, "plan", Plan(plan_id=identifier, installation_id=installation_id), value)
            result.update(plan_id=identifier, revision=value["revision"], fingerprint=review.context_fingerprint,
                state=value["state"], scopes=list(selection.scopes), expires_in_seconds=900,
                resources={name: [item.model_dump(mode='json') for item in items] for name, items in _resources(subject).items()},
                artifact_sha256=subject.binding.candidate.sha256,
                execution_class='reviewed_native', isolation_proven=False)
        return result

    def _current_plan(self, db, key, installation_id, prepared, plan_id, expected_revision, fingerprint):
        row = db.get(Plan, _identifier(plan_id), populate_existing=True)
        plan = _load(db, key, "plan", row, plan_id)
        if plan["installation_id"] != installation_id or plan["revision"] != _identifier(expected_revision):
            raise AuthorityManagementError("stale_review")
        subject = self._subject(db, key, installation_id, prepared)
        if _canonical_bytes(plan["data"]["subject"]) != _canonical_bytes(subject.model_dump(mode="json")):
            raise AuthorityManagementError("stale_review")
        native, policy = self._policy(db, key, subject, plan["data"]["native_review_id"])
        context = _parse_versioned(AuthorityReviewContextV1, AuthorityReviewContextV2, plan["data"]["context"], 'context_version', AuthorityReviewContextV3, AuthorityReviewContextV4, AuthorityReviewContextV5)
        selection = _parse_versioned(AuthoritySelectionV1, AuthoritySelectionV2, plan["data"]["selection"], 'selection_version', AuthoritySelectionV3, AuthoritySelectionV4, AuthoritySelectionV5)
        boot, now = _clock()
        review = review_authority_context(context, selection, now_ms=now)
        if (boot != plan["data"]["boot_id"] or not review.reviewable
                or _digest(fingerprint) != review.context_fingerprint or fingerprint != plan["data"]["fingerprint"]
                or native["revision"] != plan["data"]["native_revision"] or context.policy != policy):
            raise AuthorityManagementError("stale_review")
        return row, plan, subject, selection

    def decide(self, installation_id, *, actor_token, request_id, plan_id, expected_revision, fingerprint, decision):
        if decision not in {"approve", "deny", "apply"}:
            raise AuthorityManagementError("invalid_request")
        request = {"plan_id": _identifier(plan_id), "expected_revision": _identifier(expected_revision), "fingerprint": _digest(fingerprint)}
        prepared = self._prepare(installation_id)
        with self._write(installation_id, actor_token, request_id, decision, request) as (db, key, mutation, actor, result):
            if result:
                return result
            row, plan, subject, selection = self._current_plan(db, key, installation_id, prepared, plan_id, expected_revision, fingerprint)
            if plan["state"] != ("approved_pending_apply" if decision == "apply" else "review_required"):
                raise AuthorityManagementError("stale_review")
            plan["revision"] = new_authority_generation()
            plan["state"] = {"approve": "approved_pending_apply", "deny": "denied", "apply": "applied"}[decision]
            plan["data"][decision + "_actor"] = actor
            if decision == "apply":
                current = read_application_authority(db, installation_id)
                installation = db.get(ApplicationExtensionInstallation, installation_id, populate_existing=True)
                if current.mode == 'compatibility' and (installation.enabled or installation.status != 'disabled'):
                    raise AuthorityManagementError('disabled_adoption_required')
                from backend.services.application_commands import invalidate_commands
                invalidate_commands(db, installation_id)
                resulting = mutation.set_application_mode(current, "enforced")
                grant = db.get(Grant, installation_id, populate_existing=True)
                revision = grant.revision + 1 if grant is not None else 1
                if grant is None:
                    grant = Grant(installation_id=installation_id, revision=revision)
                grant.revision = revision
                value = _envelope("grant", installation_id, installation_id, "active", {
                    "subject": subject.model_dump(mode="json"), "selection": selection.model_dump(mode="json"),
                    "plan_id": plan_id, "fingerprint": fingerprint, "grant_revision": revision,
                    "authority_epoch": resulting.epoch, "native_review_id": plan["data"]["native_review_id"],
                    "native_revision": plan["data"]["native_revision"],
                    "policy": plan['data']['context']['policy']})
                _save(db, key, "grant", grant, value)
                result.update(grant_revision=revision, authority_epoch=resulting.epoch)
            _save(db, key, "plan", row, plan)
            result.update(plan_id=plan_id, revision=plan["revision"], fingerprint=fingerprint, state=plan["state"])
        return result

    def revoke_native_review(self, installation_id, *, actor_token, request_id,
            native_review_id, expected_revision):
        request = {'native_review_id': _identifier(native_review_id), 'expected_revision': _identifier(expected_revision)}
        with self._write(installation_id, actor_token, request_id, 'native_revoke', request) as (db, key, mutation, actor, result):
            if result:
                return result
            row = db.get(Native, native_review_id, populate_existing=True)
            value = _load(db, key, 'native', row, native_review_id)
            if (value['installation_id'] != installation_id or value['revision'] != expected_revision
                    or value['state'] != 'reviewed_native'):
                raise AuthorityManagementError('stale_native_review')
            value.update(state='revoked', revision=new_authority_generation())
            _save(db, key, 'native', row, value)
            current = read_application_authority(db, installation_id)
            if current.mode != 'compatibility':
                from backend.services.application_commands import invalidate_commands
                invalidate_commands(db, installation_id)
                mutation.set_application_mode(current, 'review_required')
            result.update(native_review_id=native_review_id, revision=value['revision'], state='revoked')
        return result

    @contextmanager
    def native_activation(self, installation_id, artifact_sha256, configuration, expected_guard):
        """Same reviewed artifact only; lease spans pre-helper DB admission only.

        Lifecycle invalidates the old grant. Re-enable requires a fresh permission
        review; a staged/new artifact needs the later staged lifecycle adapter.
        """
        prepared = self._prepare(installation_id)
        with self.keys.locked() as key:
            with _read_snapshot(self.engine) as db:
                from backend.services.authority_metadata import read_authority_guard
                if read_authority_guard(db) != expected_guard:
                    raise AuthorityManagementError("stale_review")
                subject = self._subject(db, key, installation_id, prepared)
                if getattr(subject, 'relational', ()):
                    raise AuthorityManagementError('relational_runtime_unavailable')
                grant = _load(db, key, "grant", db.get(Grant, installation_id), installation_id)
                self._policy(db, key, subject, grant["data"]["native_review_id"])
                proposed = key._fingerprint_in_snapshot(db, subject.binding.principal, configuration)
                if artifact_sha256 != subject.binding.candidate.sha256 or proposed != subject.binding.configuration:
                    raise AuthorityManagementError("staged_authority_not_supported")
            yield

    def revoke(self, installation_id, *, actor_token, request_id, expected_revision):
        request = {"expected_revision": _identifier(expected_revision)}
        with self._write(installation_id, actor_token, request_id, "revoke", request) as (db, key, mutation, actor, result):
            if result:
                return result
            grant = db.get(Grant, installation_id, populate_existing=True)
            value = _load(db, key, "grant", grant, installation_id)
            if value["revision"] != expected_revision or value["state"] != "active":
                raise AuthorityManagementError("stale_grant")
            value.update(state="revoked", revision=new_authority_generation())
            from backend.services.application_commands import invalidate_commands
            invalidate_commands(db, installation_id)
            current = mutation.set_application_mode(read_application_authority(db, installation_id), "review_required")
            _save(db, key, "grant", grant, value)
            result.update(state="revoked", revision=value["revision"], authority_epoch=current.epoch)
        return result

    def _require_grant(self, db, key, installation_id, prepared, scope):
        subject = self._subject(db, key, installation_id, prepared)
        current = read_application_authority(db, installation_id)
        row = db.get(Grant, installation_id, populate_existing=True)
        grant = _load(db, key, "grant", row, installation_id)
        data = grant["data"]
        from backend.services.application_authority_context import AuthorityPolicy, AuthorityPolicyV4, AuthorityPolicyV5
        approved = _parse_versioned(PolicySubjectV1, PolicySubjectV2, data["subject"], 'subject_version', PolicySubjectV3, PolicySubjectV4, PolicySubjectV5)
        native, _policy = self._policy(db, key, subject, data["native_review_id"])
        # Re-evaluate the exact approved binding with the CURRENT Core adapter.
        # Its old baseline is not rewritten to pretend this was a fresh approval.
        # Resource equality below separately pins today's effective resources.
        _, approved_policy = self._policy(db, key, approved, data['native_review_id'])
        selection = _parse_versioned(AuthoritySelectionV1, AuthoritySelectionV2, data["selection"], 'selection_version', AuthoritySelectionV3, AuthoritySelectionV4, AuthoritySelectionV5)
        if (current.mode != "enforced" or grant["state"] != "active" or row.revision != data["grant_revision"]
                or current.epoch != data["authority_epoch"] or native["revision"] != data["native_revision"]
                or approved_policy != _parse({4: AuthorityPolicyV4, 5: AuthorityPolicyV5}.get(approved.subject_version, AuthorityPolicy), data['policy'])
                or selection.selection_version != approved.subject_version
                or _resource_identity(subject) != _resource_identity(approved) or scope not in selection.scopes):
            raise AuthorityManagementError("grant_not_current")
        return grant

    def inspect(self, installation_id):
        prepared = self._prepare(installation_id)
        with self.keys.locked() as key, _read_snapshot(self.engine) as db:
            subject = self._subject(db, key, installation_id, prepared)
            row = db.get(Grant, installation_id)
            grant = None
            if row is not None:
                try:
                    grant = _load(db, key, "grant", row, installation_id)
                except (AuthorityManagementError, AuthorityReviewKeyError, ValueError, TypeError, KeyError, AttributeError):
                    # Historical seals after rotation may be unreadable. Status
                    # can offer a fresh review, but never treats them as authority.
                    pass
            native_reviews = []
            for native_row in db.scalars(select(Native).where(
                    Native.installation_id == installation_id,
                    Native.key_id == subject.binding.configuration.key_id)
                    .order_by(Native.created_at.desc(), Native.review_id).limit(32)):
                try:
                    native, _ = self._policy(db, key, subject, native_row.review_id)
                except (AuthorityManagementError, AuthorityReviewKeyError, ValueError, TypeError, KeyError, AttributeError):
                    continue  # A read-only chooser cannot promote stale/corrupt proof.
                native_reviews.append({'native_review_id': native_row.review_id,
                    'revision': native['revision']})
            effective = False
            if grant and grant["state"] == "active":
                scopes = grant["data"]["selection"]["scopes"]
                try:
                    for scope in scopes:
                        self._require_grant(db, key, installation_id, prepared, scope)
                    effective = bool(scopes) and prepared[0].status == "active" and not getattr(subject, 'relational', ())
                except (AuthorityManagementError, AuthorityReviewKeyError, ValueError, TypeError, KeyError, AttributeError):
                    pass
            installation = db.get(ApplicationExtensionInstallation, installation_id)
            return {"installation_id": installation_id, "mode": subject.binding.baseline.enforcement_mode,
                "installation_status": installation.status, "installation_enabled": installation.enabled,
                "native_reviews": native_reviews,
                "artifact_sha256": subject.binding.candidate.sha256, "scopes": sorted(_subject_scopes(subject)),
                "grant_revision": row.revision if row else None, "grant_record_revision": grant["revision"] if grant else None,
                "grant_effective": effective and installation.enabled,
                "grant_state": grant["state"] if grant else ('unavailable' if row else None),
                "execution_class": "reviewed_native_only", "isolation_proven": False,
                **({'runtime_blockers': ['relational_runtime_unavailable']} if getattr(subject, 'relational', ()) else {})}


def configured_manager(engine):
    from backend.config import get_settings
    from backend.version import core_version
    settings = get_settings()
    default = Path(engine.url.database).resolve().parent / "authority-review" if engine.dialect.name == "sqlite" else Path("/var/lib/3mm/core/authority-review")
    directory = Path(os.environ.get("THREE_MM_AUTHORITY_REVIEW_KEY_DIR", str(default)))
    return ApplicationAuthorityManager(engine, uploads_root=settings.backend.uploads_dir,
        core_version=core_version(), review_key_directory=directory)


@contextmanager
def effect_admission(db, installation_id, scope):
    """Key/guard stay held through caller's durable admission, never HTTP I/O.

    Compatibility is unchanged. Opt-in grants never fall back to legacy access.
    Caller MUST commit its queue/attempt/one-use permit before close/release.
    """
    if isinstance(scope, str) and scope.startswith('storage:relational_'):
        # These grants are review metadata until the bounded transaction/lifecycle
        # adapter exists. Never issue a compatibility or generic effect lease.
        raise ValueError('Relational storage runtime is not implemented')
    with db.no_autoflush:
        mode = db.scalar(select(ApplicationExtensionInstallation.authority_mode).where(ApplicationExtensionInstallation.id == installation_id))
    if mode == "compatibility":
        def release():
            pass
        release.definition, release.compatibility = None, True
        yield release
        return
    if mode != "enforced":
        raise ValueError("Application resource grant is unavailable or stale")
    if db.new or db.dirty or db.deleted:
        raise ValueError('Application authority admission requires a clean session')
    released = False
    try:
        manager = configured_manager(db.get_bind().engine)
        prepared = manager._prepare(installation_id)  # ZIP outside key/guard.
        with ExitStack() as lease:
            key = lease.enter_context(manager.keys.locked())
            if db.execute(update(CoreAuthorityGuard).where(CoreAuthorityGuard.singleton_id == 1)
                    .values(revision=CoreAuthorityGuard.revision)).rowcount != 1:
                raise AuthorityManagementError()
            manager._require_grant(db, key, installation_id, prepared, scope)
            installation = db.get(ApplicationExtensionInstallation, installation_id, populate_existing=True)
            if not installation.enabled or installation.status != "active":
                raise AuthorityManagementError("installation_inactive")
            def release():
                nonlocal released
                released = True
                lease.close()  # Durable attempt/queue/permit committed first.
            release.definition, release.compatibility = prepared[1].application_extension, False
            release.publications = prepared[1].application_publications
            yield release
    except (AuthorityManagementError, AuthorityReviewKeyError, SQLAlchemyError, ValueError, OSError):
        if released:
            raise
        db.rollback()
        raise ValueError("Application resource grant is unavailable or stale") from None


def lock_compatibility_admission(db, installation, *, required=False):
    """Linearize legacy connector admission against adoption/disable/rotation.

    Row-only lock: no later guard acquisition in this path. Admission committed
    before adoption may finish; adoption cannot recall an already admitted POST.
    """
    if installation.authority_mode != "compatibility":
        if required:
            raise ValueError("Application changed before legacy admission")
        return
    changed = db.execute(update(ApplicationExtensionInstallation).where(
        ApplicationExtensionInstallation.id == installation.id,
        ApplicationExtensionInstallation.authority_mode == "compatibility",
        ApplicationExtensionInstallation.authority_epoch == installation.authority_epoch,
        ApplicationExtensionInstallation.module_package_id == installation.module_package_id,
        ApplicationExtensionInstallation.enabled.is_(True),
        ApplicationExtensionInstallation.status == "active")
        .values(authority_epoch=ApplicationExtensionInstallation.authority_epoch,
            updated_at=ApplicationExtensionInstallation.updated_at)
        .execution_options(synchronize_session=False)).rowcount
    if changed != 1:
        raise ValueError("Application changed before connector admission")
