"""Explicit, sealed command-resource replacement through a fenced restart.

The new grant and active configuration become effective together, only after the
helper confirms activation and Core rechecks the approved resources. A lost
reply never retries activation. Recovery only proves quiescence; fresh consent
and activation are required afterward. No raw configuration is stored in plans.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.application_authority_grant import ApplicationAuthorityPlan as Plan, ApplicationAuthorityGrant as Grant
from backend.db.device import Device
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.services import application_authority_management as authority
from backend.services import application_authority_sources as sources
from backend.services.application_authority_context import _canonical_bytes
from backend.services.application_authority_inspection import AuthorityInspectionBaseline, _read_baseline
from backend.services.application_command_discovery import _binding, _candidate
from backend.services.application_consent import TTL_MS, _human_grants
from backend.services.application_lifecycle import (
    _LifecycleTicket, _helper_lifecycle, _lifecycle_state, _package_state,
    _start_lifecycle, _lock_lifecycle, _lifecycle_audit,
)
from backend.services.application_policy_reviews import _actor, PolicyReviewStoreError
from backend.services.authority_metadata import authority_transaction, read_application_authority, read_authority_guard
from three_mm_protocol.application_command_discovery import DeviceId
from pydantic import TypeAdapter
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError

KIND = "administrator_command_rebind"
PENDING = {"applying", "recovering", "recovery_required"}


def _digest(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _actor_now(db, token):
    try:
        return list(_actor(db, token))
    except PolicyReviewStoreError:
        raise authority.AuthorityManagementError("actor_unavailable") from None


def _plan(db, key, installation_id, plan_id):
    row = db.get(Plan, authority._identifier(plan_id), populate_existing=True)
    plan = authority._load(db, key, "plan", row, plan_id)
    if plan["installation_id"] != installation_id or plan["data"].get("kind") != KIND:
        raise authority.AuthorityManagementError("record_unavailable")
    return row, plan


def _transition(db, key, row, plan, state):
    plan.update(state=state, revision=authority.new_authority_generation())
    authority._save(db, key, "plan", row, plan)


def _selection(manager, db, key, subject, grant, issued, expires, now):
    native, policy = manager._policy(db, key, subject, grant["data"]["native_review_id"])
    if native["revision"] != grant["data"]["native_revision"]:
        raise authority.AuthorityManagementError("native_review_unavailable")
    version = subject.subject_version
    selection = authority._parse(getattr(authority, "AuthoritySelectionV" + str(version)), grant["data"]["selection"])
    context_model = getattr(authority, "AuthorityReviewContextV" + str(version))
    context = context_model(context_version=version,
        **subject.binding.model_dump(exclude={"recovery_generation"}), policy=policy,
        issued_at_ms=issued, expires_at_ms=expires, **authority._resources(subject))
    if not authority.review_authority_context(context, selection, now_ms=now).reviewable:
        raise authority.AuthorityManagementError("selection_not_allowed")
    return policy


def _proposal(manager, db, key, installation_id, prepared, binding_id, device_id):
    if (prepared.pin.status, prepared.pin.enabled) != ("active", True):
        raise authority.AuthorityManagementError("installation_inactive")
    definition = prepared.package.application_extension
    binding = _binding(definition, binding_id)
    device_id = TypeAdapter(DeviceId).validate_python(device_id)
    current = manager._subject(db, key, installation_id, prepared)
    # Relational activation has a separate data-migration/recovery contract.
    if getattr(current, "relational", ()):
        raise authority.AuthorityManagementError("unsupported_authority")
    configuration = sources._configuration(db, installation_id, prepared.package)
    if configuration[binding.target_device_config_key] == device_id:
        raise authority.AuthorityManagementError("binding_unchanged")
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None or not _candidate(db, binding, device, datetime.now(UTC)).selectable:
        raise authority.AuthorityManagementError("resource_unavailable")
    configuration = {**configuration, binding.target_device_config_key: device_id}
    proposed = manager._subject(db, key, installation_id, prepared, proposed_configuration=configuration)
    # A shared config key must not silently rebind other declared resources.
    def other_resources(subject):
        return {name: [item.model_dump(mode="json") for item in items
            if name != "commands" or item.declaration.binding_id != binding_id]
            for name, items in authority._resources(subject).items()}
    if other_resources(current) != other_resources(proposed):
        raise authority.AuthorityManagementError("binding_change_not_isolated")
    return current, proposed, configuration


def preview(manager, installation_id, *, actor_token, request_id, binding_id, device_id):
    prepared = manager._prepare(installation_id)
    request = {"binding_id": binding_id, "device_id": device_id}
    with manager._write(installation_id, actor_token, request_id, "command_rebind_preview", request) as (db, key, mutation, actor, result):
        if result:
            return result
        grant = manager._require_grant(db, key, installation_id, prepared, "command:" + binding_id)
        current, proposed, _ = _proposal(manager, db, key, installation_id, prepared, binding_id, device_id)
        boot, now = authority._clock()
        _selection(manager, db, key, proposed, grant, now, now + TTL_MS, now)
        identifier = authority.new_authority_generation()
        data = {"kind": KIND, **request, "actor": actor, "boot_id": boot,
            "issued_at_ms": now, "expires_at_ms": now + TTL_MS,
            "guard_generation": mutation.guard.generation, "guard_revision": mutation.guard.revision + 1,
            "before": current.model_dump(mode="json"), "after": proposed.model_dump(mode="json"),
            "grant_revision": grant["revision"], "current_user_grants": _human_grants(db, installation_id, actor[0])}
        fingerprint = _digest(data)
        data["fingerprint"] = fingerprint
        plan = authority._envelope("plan", identifier, installation_id, "preview", data)
        authority._save(db, key, "plan", Plan(plan_id=identifier, installation_id=installation_id), plan)
        binding = _binding(prepared.package.application_extension, binding_id)
        before_device = next(item.target_device_id for item in current.commands if item.declaration.binding_id == binding_id)
        def provider(device_id):
            device = db.scalar(select(Device).where(Device.device_id == device_id))
            return _candidate(db, binding, device, datetime.now(UTC)).model_dump(mode="json")
        result.update(rebinding_version=1, module_id=prepared.pin.module_id,
            preview_id=identifier, revision=plan["revision"], fingerprint=fingerprint,
            binding_id=binding_id, artifact_sha256=prepared.pin.sha256,
            before=next(item.model_dump(mode="json") for item in current.commands if item.declaration.binding_id == binding_id),
            after=next(item.model_dump(mode="json") for item in proposed.commands if item.declaration.binding_id == binding_id),
            before_provider=provider(before_device), after_provider=provider(device_id),
            scopes=grant["data"]["selection"]["scopes"], expires_in_seconds=TTL_MS // 1000,
            restart_required=True)
    return result


def _state_identity(db, key, data, installation):
    # HMAC fingerprint keeps low-entropy secrets out of both plan and audit.
    from backend.services.application_authority_context import AuthorityPrincipal
    principal = authority._parse(AuthorityPrincipal, data["after"]["binding"]["principal"])
    return key._fingerprint_in_snapshot(db, principal,
        {"lifecycle_state": list(_lifecycle_state(installation))}).model_dump(mode="json")


def _pin_ticket(db, key, data, installation, ticket):
    data.update(ticket=_helper_lifecycle(ticket), operation=ticket.operation, authority_mode=ticket.application.mode,
        state_identity=_state_identity(db, key, data, installation),
        package_identity=_digest(_package_state(db.get(ModulePackage, installation.module_package_id))))


def _pending_ticket(db, key, mutation, plan):
    data = plan["data"]
    installation = db.get(Installation, plan["installation_id"], populate_existing=True)
    if installation is None:
        raise authority.AuthorityManagementError("stale_review")
    current = read_application_authority(db, installation.id)
    ticket = _LifecycleTicket(current, data["operation"], _lifecycle_state(installation), mutation.guard.generation)
    if (plan["state"] not in PENDING or _helper_lifecycle(ticket) != data["ticket"]
            or installation.status != data["operation"] or current.mode != data["authority_mode"]
            or _state_identity(db, key, data, installation) != data["state_identity"]
            or _digest(_package_state(db.get(ModulePackage, installation.module_package_id))) != data["package_identity"]):
        raise authority.AuthorityManagementError("stale_review")
    return ticket


def _status(plan, app):
    return {"rebinding_version": 1, "module_id": app.module_id,
        "preview_id": plan["record_id"], "revision": plan["revision"], "state": plan["state"],
        "installation_status": app.status, "installation_enabled": app.enabled,
        "binding_id": plan["data"]["binding_id"], "device_id": plan["data"]["device_id"],
        "recovery_required": plan["state"] in PENDING, "access": "not_evaluated"}


def status(manager, installation_id, *, plan_id):
    with manager.keys.locked() as key, sources._read_snapshot(manager.engine) as db:
        _, plan = _plan(db, key, installation_id, plan_id)
        return _status(plan, db.get(Installation, installation_id))


def pending(manager, installation_id):
    """Find the current interrupted change after a browser/process restart.

    Canonical text predicates only narrow the bounded query. Every returned plan
    is authenticated and matched to the current installation/epoch/guard. This
    read neither initializes a key nor authorizes recovery or execution.
    """
    with manager.keys.locked() as key, sources._read_snapshot(manager.engine) as db:
        app = db.get(Installation, installation_id)
        current = read_application_authority(db, installation_id)
        guard = read_authority_guard(db)
        if app.enabled or app.status not in {"activating", "recovering", "recovery_required"}:
            return {"pending": None}
        rows = db.scalars(select(Plan).where(Plan.installation_id == installation_id,
            Plan.payload.contains('"kind":"' + KIND + '"'),
            or_(*(Plan.payload.contains('"state":"' + state + '"') for state in sorted(PENDING))))
            .order_by(Plan.created_at.desc(), Plan.plan_id.desc()).limit(32))
        for row in rows:
            _, plan = _plan(db, key, installation_id, row.plan_id)
            data = plan["data"]
            ticket = {"installation_id": installation_id, "module_id": app.module_id,
                "instance_id": app.instance_id, "incarnation": current.incarnation,
                "epoch": current.epoch, "guard_generation": guard.generation}
            if (plan["state"] in PENDING and data.get("ticket") == ticket
                    and data.get("operation") == app.status and data.get("authority_mode") == current.mode):
                return {"pending": _status(plan, app)}
        return {"pending": None}


def _failed(manager, installation_id, plan_id, expected_revision):
    with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db) as mutation:
        row, plan = _plan(db, key, installation_id, plan_id)
        if plan["revision"] != expected_revision:
            return  # A newer explicit recovery already superseded this work.
        ticket = _pending_ticket(db, key, mutation, plan)
        app = _lock_lifecycle(db, mutation, ticket)
        app.status, app.enabled = "recovery_required", False
        app.error = "Resource change outcome is unconfirmed; explicit recovery is required"
        db.flush()
        ticket = _LifecycleTicket(read_application_authority(db, installation_id), app.status,
            _lifecycle_state(app), mutation.guard.generation)
        _pin_ticket(db, key, plan["data"], app, ticket)
        _transition(db, key, row, plan, "recovery_required")
        _lifecycle_audit(db, plan["data"]["actor"][0], app.module_id,
            "APPLICATION_COMMAND_REBIND_FAILED", preview_id=plan_id, outcome="unconfirmed")


def _refresh_artifact(manager, prepared):
    pin = prepared.pin
    package = _read_baseline(AuthorityInspectionBaseline(pin.module_id, pin.version,
        pin.sha256, pin.active_version, pin.status, None), manager.uploads_root, manager.core_version)
    build = None
    if package.compiled_ui is not None:
        from backend.services.compiled_ui import load_compiled_ui_artifact
        build = load_compiled_ui_artifact(package).built_ui_sha256
    return authority._PreparedAuthority(pin, package, build)


def apply(manager, installation_id, *, actor_token, request_id, preview_id,
        expected_revision, fingerprint, approve_change):
    if approve_change is not True:
        raise authority.AuthorityManagementError("resource_consent_required")
    request = {"preview_id": authority._identifier(preview_id),
        "expected_revision": authority._identifier(expected_revision),
        "fingerprint": authority._digest(fingerprint), "approve_change": True}
    # Replayed receipts must work even while the installation is interrupted.
    try:
        prepared, prepare_error = manager._prepare(installation_id), None
    except authority.AuthorityManagementError as exc:
        prepared, prepare_error = None, exc
    with manager._write(installation_id, actor_token, request_id, "command_rebind_apply", request) as (db, key, mutation, actor, result):
        if result:
            return result  # Historical only: never repeat helper I/O.
        if prepare_error is not None:
            raise prepare_error
        row, plan = _plan(db, key, installation_id, preview_id)
        data = plan["data"]
        boot, now = authority._clock()
        if (plan["state"] != "preview" or plan["revision"] != expected_revision
                or data["actor"] != actor or data["boot_id"] != boot
                or not data["issued_at_ms"] <= now < data["expires_at_ms"]
                or data["guard_generation"] != mutation.guard.generation
                or data["guard_revision"] != mutation.guard.revision
                or data["fingerprint"] != fingerprint
                or _digest({name: value for name, value in data.items() if name != "fingerprint"}) != fingerprint):
            raise authority.AuthorityManagementError("stale_review")
        grant = manager._require_grant(db, key, installation_id, prepared, "command:" + data["binding_id"])
        before, after, configuration = _proposal(manager, db, key, installation_id, prepared, data["binding_id"], data["device_id"])
        if (grant["revision"] != data["grant_revision"]
                or before.model_dump(mode="json") != data["before"] or after.model_dump(mode="json") != data["after"]
                or _human_grants(db, installation_id, actor[0]) != data["current_user_grants"]):
            raise authority.AuthorityManagementError("stale_review")
        _selection(manager, db, key, after, grant, data["issued_at_ms"], data["expires_at_ms"], now)
        app = db.get(Installation, installation_id)
        app.configuration = configuration
        ticket = _start_lifecycle(db, mutation, app, "activating", actor[0])
        _pin_ticket(db, key, data, app, ticket)
        _transition(db, key, row, plan, "applying")
        pending_revision = plan["revision"]
        result.update(preview_id=preview_id, state="applying", revision=pending_revision)
    helper = UpdateHelperClient(get_settings().applications.helper_socket,
        timeout_seconds=prepared.package.application_extension.service.startup_timeout_seconds + 10)
    try:
        response = helper.activate_application_extension(prepared.pin.sha256, actor[0], configuration, _helper_lifecycle(ticket))
        if (not isinstance(response, dict) or response.get("module_id") != prepared.pin.module_id
                or response.get("version") != prepared.pin.version
                or response.get("sha256") != prepared.pin.sha256
                or response.get("instance_id") != ticket.state[2]
                or not isinstance(response.get("socket_path"), str) or not response["socket_path"]):
            raise UpdateHelperError("Activation identity did not match the approved change")
        prepared = _refresh_artifact(manager, prepared)
        with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db) as mutation:
            row, plan = _plan(db, key, installation_id, preview_id)
            if plan["revision"] != pending_revision:
                raise authority.AuthorityManagementError("stale_review")
            data = plan["data"]
            if _actor_now(db, actor_token) != data["actor"]:
                raise authority.AuthorityManagementError("actor_unavailable")
            ticket = _pending_ticket(db, key, mutation, plan)
            app = _lock_lifecycle(db, mutation, ticket)
            app.active_version, app.status, app.enabled = prepared.pin.version, "active", True
            app.socket_path = response["socket_path"]
            app.activated_at = app.health_checked_at = datetime.now(UTC)
            app.error = None
            db.flush()
            prepared = replace(prepared, pin=sources._package_pin(db, installation_id))
            subject = manager._subject(db, key, installation_id, prepared)
            approved = authority._parse(type(subject), data["after"])
            old = authority._load(db, key, "grant", db.get(Grant, installation_id), installation_id)
            boot, now = authority._clock()
            if (old["revision"] != data["grant_revision"] or old["state"] != "active"
                    or authority._resource_identity(subject) != authority._resource_identity(approved)
                    or boot != data["boot_id"]
                    or _human_grants(db, installation_id, actor[0]) != data["current_user_grants"]):
                raise authority.AuthorityManagementError("stale_review")
            policy = _selection(manager, db, key, approved, old, data["issued_at_ms"], data["expires_at_ms"], now)
            grant_row = db.get(Grant, installation_id)
            if grant_row.revision != old["data"]["grant_revision"]:
                raise authority.AuthorityManagementError("grant_not_current")
            grant_row.revision += 1
            grant_data = deepcopy(old["data"])
            grant_data.update(subject=data["after"], policy=policy.model_dump(mode="json"),
                plan_id=preview_id, fingerprint=fingerprint, grant_revision=grant_row.revision,
                authority_epoch=read_application_authority(db, installation_id).epoch,
                resource_consent_kind=KIND, resource_consent_actor=actor)
            authority._save(db, key, "grant", grant_row,
                authority._envelope("grant", installation_id, installation_id, "active", grant_data))
            _transition(db, key, row, plan, "completed")
            _lifecycle_audit(db, actor[0], app.module_id, "APPLICATION_COMMAND_REBOUND",
                preview_id=preview_id, binding_id=data["binding_id"], grant_revision=grant_row.revision)
    except Exception:
        # Durable applying remains a safe recovery point even if key/DB failure
        # prevents recording the more descriptive recovery_required state.
        _failed(manager, installation_id, preview_id, pending_revision)
        raise authority.AuthorityManagementError("recovery_required") from None
    return status(manager, installation_id, plan_id=preview_id)


def recover(manager, installation_id, *, actor_token, preview_id, expected_revision,
        confirmed_external_outcome_reviewed):
    if confirmed_external_outcome_reviewed is not True:
        raise authority.AuthorityManagementError("external_outcome_review_required")
    authority._identifier(expected_revision)
    with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db) as mutation:
        actor = _actor_now(db, actor_token)
        row, plan = _plan(db, key, installation_id, preview_id)
        if plan["revision"] != expected_revision:
            raise authority.AuthorityManagementError("stale_review")
        ticket = _pending_ticket(db, key, mutation, plan)
        app = _lock_lifecycle(db, mutation, ticket)
        ticket = _start_lifecycle(db, mutation, app, "recovering", actor[0])
        _pin_ticket(db, key, plan["data"], app, ticket)
        _transition(db, key, row, plan, "recovering")
        revision = plan["revision"]
    context = _helper_lifecycle(ticket)
    try:
        helper = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=45)
        response = helper.recover_application_extension(context["instance_id"], actor[0], context)
        if (not isinstance(response, dict) or response.get("status") != "disabled"
                or response.get("instance_id") != context["instance_id"]
                or response.get("lifecycle") != context or response.get("quiescent") is not True):
            raise UpdateHelperError("Quiescence was not confirmed")
        with manager.keys.locked() as key, Session(manager.engine) as db, authority_transaction(db) as mutation:
            row, plan = _plan(db, key, installation_id, preview_id)
            if plan["revision"] != revision:
                raise authority.AuthorityManagementError("stale_review")
            ticket = _pending_ticket(db, key, mutation, plan)
            app = _lock_lifecycle(db, mutation, ticket)
            app.status, app.enabled, app.error = "disabled", False, None
            app.health_checked_at = None
            # Config-only replacement pins the same artifact throughout. Keep
            # its version so ordinary fresh consent can inspect the stopped app.
            _transition(db, key, row, plan, "recovered_disabled")
            _lifecycle_audit(db, actor[0], app.module_id, "APPLICATION_COMMAND_REBIND_RECOVERED",
                preview_id=preview_id, external_outcome_reviewed=True, fresh_consent_required=True)
    except Exception:
        _failed(manager, installation_id, preview_id, revision)
        raise authority.AuthorityManagementError("recovery_required") from None
    return status(manager, installation_id, plan_id=preview_id)
