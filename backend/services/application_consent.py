"""Exact installed-package administrator consent, separate from manual code review.

Preview may create the missing Core-owned sealing key, but grants no package trust
or resources. Allow rechecks the current actor, package, resources and preview in
one key/authority transaction; it never starts a service or claims isolation.
"""
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import (
    ApplicationAuthorityPlan as Plan, ApplicationAuthorityGrant as Grant,
    ApplicationNativeReview as Native,
)
from backend.db.audit_log import AuditLog
from backend.db.module import ApplicationExtensionInstallation, ApplicationPermissionGrant
from backend.services import application_authority_management as authority
from backend.services.application_authority_context import _canonical_bytes
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_policy_reviews import _actor, PolicyReviewStoreError
from backend.services.authority_metadata import authority_transaction, read_application_authority

KIND = "administrator_package_consent"
TTL_MS = 900_000


def _bootstrap_key(manager, actor_token):
    # First provision only. Existing malformed/foreign/stale material is never
    # replaced. A crash between file creation/audit leaves infrastructure only.
    try:
        with Session(manager.engine) as db, authority_transaction(db):
            _actor(db, actor_token)
        try:
            manager.keys.identity()
            return
        except AuthorityReviewKeyError:
            identity = manager.keys.provision()
        with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db) as mutation:
            actor = _actor(db, actor_token)
            key._check(db)
            db.add(AuditLog(user_id=actor[0], action="APPLICATION_AUTHORITY_KEY",
                entity_type="core_authority", changes={"key_id": identity.key_id,
                    "operation": "consent_first_provision", "permission_approval": "not_evaluated"}))
            mutation.advance_guard_revision()
    except PolicyReviewStoreError:
        raise authority.AuthorityManagementError("actor_unavailable") from None


def _permissions(prepared):
    values = []
    for item in prepared.package.application_extension.permissions:
        values.append({"permission_id": item.permission_id, "name": item.label.en})
    return sorted(values, key=lambda item: item["permission_id"])


def _human_grants(db, installation_id, actor_id):
    return sorted(db.scalars(select(ApplicationPermissionGrant.permission_id).where(
        ApplicationPermissionGrant.application_installation_id == installation_id,
        ApplicationPermissionGrant.user_id == actor_id)))


def _saved_selection(manager, db, key, installation_id, subject):
    try:
        value = authority._load(db, key, "grant", db.get(Grant, installation_id), installation_id)
        if value["state"] != "active":
            return None
        data = value["data"]
        approved = authority._parse(getattr(authority, 'PolicySubjectV' + str(data['subject']['subject_version'])), data['subject'])
        native, _ = manager._policy(db, key, subject, data["native_review_id"])
        if (authority._resource_identity(subject, required_only=True) != authority._resource_identity(approved, required_only=True)
                or native["revision"] != data["native_revision"]):
            return None
        return data
    except (authority.AuthorityManagementError, AuthorityReviewKeyError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _fingerprint(data):
    return hashlib.sha256(b"3mm:administrator-package-consent:v1\x00" + _canonical_bytes(data)).hexdigest()


def preview(manager, installation_id, *, actor_token, request_id):
    authority._identifier(request_id)
    _bootstrap_key(manager, actor_token)
    prepared = manager._prepare(installation_id)
    with manager._write(installation_id, actor_token, request_id, "consent_preview", {}) as (db, key, mutation, actor, result):
        if result:
            return result
        unavailable = []
        subject = manager._subject(db, key, installation_id, prepared, diagnostics=unavailable)
        permissions = _permissions(prepared)
        current_human = _human_grants(db, installation_id, actor[0])
        saved = _saved_selection(manager, db, key, installation_id, subject)
        scopes = sorted(authority._subject_scopes(subject))
        selected = [scope for scope in saved['selection']['scopes'] if scope in scopes
            and authority.optional_scope_current(subject, {'data':saved}, scope)] if saved else [scope for scope in scopes
            if scope not in {'storage:private_files_publish', 'storage:private_files_transform'}
            and scope not in subject.optional_resources and not scope.startswith('query:')]
        known_permissions = [item["permission_id"] for item in permissions]
        user_saved = bool(current_human) or bool(saved and saved.get("actor_user_id") == actor[0])
        selected_human = [item for item in current_human if item in known_permissions] if user_saved else known_permissions
        boot, now = authority._clock()
        identifier = authority.new_authority_generation()
        data = {"kind": KIND, "subject": subject.model_dump(mode="json"),
            "actor": actor, "guard_generation": mutation.guard.generation,
            "guard_revision": mutation.guard.revision + 1, "boot_id": boot,
            "issued_at_ms": now, "expires_at_ms": now + TTL_MS,
            "user_permissions": permissions, "current_user_grants": current_human}
        fingerprint = _fingerprint(data)
        data["fingerprint"] = fingerprint
        value = authority._envelope("plan", identifier, installation_id, "consent_preview", data)
        authority._save(db, key, "plan", Plan(plan_id=identifier, installation_id=installation_id), value)
        installation = db.get(ApplicationExtensionInstallation, installation_id)
        access_saved = saved is not None
        if access_saved and installation.active_version is None:
            # A recovered/unactivated candidate cannot renew an obsolete grant
            # as an ordinary disable/enable cycle can. Keep the saved choices
            # visible, but require explicit current consent before activation.
            try:
                manager._require_current_grant(db, key, installation_id, prepared)
            except (authority.AuthorityManagementError, AuthorityReviewKeyError, ValueError, TypeError, KeyError, AttributeError):
                access_saved = False
        result.update(consent_version=1, preview_id=identifier, revision=value["revision"],
            fingerprint=fingerprint, expires_in_seconds=TTL_MS // 1000,
            module_id=subject.binding.principal.module_id, installation_id=installation_id,
            artifact_sha256=subject.binding.candidate.sha256,
            built_ui_sha256=subject.binding.candidate.built_ui_sha256,
            scopes=scopes, selected_scopes=sorted(selected),
            optional_resources=list(subject.optional_resources),
            unavailable_resources=unavailable,
            resources={name: [item.model_dump(mode="json") for item in items]
                for name, items in authority._resources(subject).items()},
            user_permissions=permissions, selected_user_permissions=selected_human,
            access_saved=access_saved, installation_enabled=installation.enabled,
            installation_status=installation.status)
    return result


def allow(manager, installation_id, *, actor_token, request_id, preview_id,
        expected_revision, fingerprint, scopes, user_permissions, accept_native_code):
    if accept_native_code is not True:
        raise authority.AuthorityManagementError("native_consent_required")
    request = {"preview_id": authority._identifier(preview_id),
        "expected_revision": authority._identifier(expected_revision), "fingerprint": authority._digest(fingerprint),
        "scopes": scopes, "user_permissions": user_permissions, "accept_native_code": True}
    if (type(scopes) is not list or any(type(item) is not str for item in scopes)
            or type(user_permissions) is not list or any(type(item) is not str for item in user_permissions)
            or len(user_permissions) > 96 or len(user_permissions) != len(set(user_permissions))):
        raise authority.AuthorityManagementError("invalid_request")
    prepared = manager._prepare(installation_id)
    with manager._write(installation_id, actor_token, request_id, "consent_allow", request) as (db, key, mutation, actor, result):
        if result:
            return result
        row = db.get(Plan, preview_id, populate_existing=True)
        plan = authority._load(db, key, "plan", row, preview_id)
        data = plan["data"]
        boot, now = authority._clock()
        if (plan["installation_id"] != installation_id or plan["state"] != "consent_preview"
                or plan["revision"] != expected_revision or data.get("kind") != KIND
                or data["actor"] != actor or data["boot_id"] != boot
                or not data["issued_at_ms"] <= now < data["expires_at_ms"]
                or data["guard_generation"] != mutation.guard.generation
                or data["guard_revision"] != mutation.guard.revision
                or data["fingerprint"] != fingerprint
                or _fingerprint({name: value for name, value in data.items() if name != "fingerprint"}) != fingerprint):
            raise authority.AuthorityManagementError("stale_review")
        subject = manager._subject(db, key, installation_id, prepared)
        permissions = _permissions(prepared)
        if (_canonical_bytes(data["subject"]) != _canonical_bytes(subject.model_dump(mode="json"))
                or data["user_permissions"] != permissions
                or data["current_user_grants"] != _human_grants(db, installation_id, actor[0])):
            raise authority.AuthorityManagementError("stale_review")
        known_scopes = set(authority._subject_scopes(subject))
        if set(scopes) - known_scopes or set(user_permissions) - {item["permission_id"] for item in permissions}:
            raise authority.AuthorityManagementError("selection_not_allowed")
        selection = authority._parse(getattr(authority, "AuthoritySelectionV" + str(subject.subject_version)),
            {"selection_version": subject.subject_version, "scopes": scopes})
        native_id = authority.new_authority_generation()
        native_data = {"binding": authority._native_binding(subject), "actor": actor,
            "review_kind": "authenticated_administrator_package_consent",
            "artifact_sha256": subject.binding.candidate.sha256,
            "accepts_native_host_risk": True, "accepts_same_origin_ui_risk": subject.has_executable_frontend,
            "isolation_proven": False}
        if subject.has_executable_frontend:
            native_data["built_ui_sha256"] = subject.binding.candidate.built_ui_sha256
        native = authority._envelope("native", native_id, installation_id, "administrator_approved", native_data)
        authority._save(db, key, "native", Native(review_id=native_id, installation_id=installation_id), native)
        _, policy = manager._policy(db, key, subject, native_id)
        if set(selection.scopes) - set(policy.allowed_scopes) or policy.required_scopes:
            raise authority.AuthorityManagementError("selection_not_allowed")
        # Optional consent still obeys the platform's exact resource contracts,
        # including whole relational profiles and canonical connector origins.
        context_model = getattr(authority, "AuthorityReviewContextV" + str(subject.subject_version))
        context = context_model(context_version=subject.subject_version,
            **subject.binding.model_dump(exclude={"recovery_generation"}), policy=policy,
            issued_at_ms=data["issued_at_ms"], expires_at_ms=data["expires_at_ms"],
            **authority._resources(subject))
        context = authority._parse(context_model, context)
        review = authority.review_authority_context(context, selection, now_ms=now)
        if not review.reviewable:
            raise authority.AuthorityManagementError("selection_not_allowed")
        from backend.services.application_commands import invalidate_commands
        invalidate_commands(db, installation_id)
        resulting = mutation.set_application_mode(read_application_authority(db, installation_id), "enforced")
        grant = db.get(Grant, installation_id, populate_existing=True)
        revision = grant.revision + 1 if grant is not None else 1
        if grant is None:
            grant = Grant(installation_id=installation_id, revision=revision)
        grant.revision = revision
        grant_data = {"subject": subject.model_dump(mode="json"), "selection": selection.model_dump(mode="json"),
            "plan_id": preview_id, "fingerprint": fingerprint, "grant_revision": revision,
            "authority_epoch": resulting.epoch, "native_review_id": native_id,
            "native_revision": native["revision"], "policy": policy.model_dump(mode="json"),
            "consent_kind": KIND, "actor_user_id": actor[0], "user_permissions": sorted(user_permissions)}
        value = authority._envelope("grant", installation_id, installation_id, "active", grant_data)
        authority._save(db, key, "grant", grant, value)
        current_grants = list(db.scalars(select(ApplicationPermissionGrant).where(
            ApplicationPermissionGrant.application_installation_id == installation_id,
            ApplicationPermissionGrant.user_id == actor[0])))
        existing = {item.permission_id for item in current_grants}
        for item in current_grants:
            if item.permission_id not in user_permissions:
                db.delete(item)
        for permission_id in set(user_permissions) - existing:
            db.add(ApplicationPermissionGrant(application_installation_id=installation_id,
                user_id=actor[0], permission_id=permission_id, granted_by=actor[0]))
        plan.update(state="consent_applied", revision=authority.new_authority_generation())
        data.update(allow_actor=actor, selected_scopes=list(selection.scopes), selected_user_permissions=sorted(user_permissions))
        authority._save(db, key, "plan", row, plan)
        installation = db.get(ApplicationExtensionInstallation, installation_id)
        result.update(consent_version=1, module_id=subject.binding.principal.module_id,
            installation_id=installation_id, saved=True, effective=False, preview_id=preview_id,
            grant_revision=revision, grant_record_revision=value["revision"], authority_epoch=resulting.epoch,
            installation_enabled=installation.enabled, installation_status=installation.status)
    # An observation failure after durable approval cannot turn approval into a
    # failed mutation. Runtime/provider availability remains separate from consent.
    try:
        status = manager.inspect(installation_id)
        result = {**result, "effective": status["grant_effective"]}
    except (authority.AuthorityManagementError, AuthorityReviewKeyError, ValueError, TypeError, KeyError, AttributeError, OSError):
        pass
    return result
