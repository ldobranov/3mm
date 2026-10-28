"""Core-owned, one-consumption delegation of an exact ordinary app operation.

Uses the existing sealed action journal. A request ID is not a bearer credential;
HTTP readers need the originating login, executors the owning app's signed IPC.
"""
import asyncio
import hashlib
import json
import os
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.db.session import UserSession
from backend.db.audit_log import AuditLog
from backend.db.user import User
from backend.services import application_authority_management as authority
from backend.services.application_access import ApplicationPrincipal, application_permission_ids, can_access_application_route, can_access_application_operation, validate_application_login
from backend.services.application_extensions import find_operation, validate_operation_payload
from backend.services.application_invocation_relay import InvocationSpec, invoke_with_relay
from backend.services.authority_metadata import authority_transaction, read_application_authority, read_authority_guard
from backend.utils.jwt_utils import decode_token
from three_mm_protocol.application_delegation import DelegationCreateV1, DelegationReceiptV1, OperationDelegationV1, OperationExecutorV1, bounded_object
from three_mm_runtime.application_transport import ApplicationServiceClient
from three_mm_platform_wire import process_generation

KIND = "operation_delegation"
MAX_RECORDS = 4096


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def login_actor(db, authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "A current tracked user login is required")
    claims = decode_token(authorization.split(" ", 1)[1].strip())
    user = validate_application_login(claims, db)
    if type(claims.get("sid")) is not int or claims["sid"] < 1:
        raise HTTPException(401, "A current tracked user login is required")
    return {"user_id": user.id, "subject_id": user.subject_id, "sid": claims["sid"], "token_version": user.token_version, "jti": claims["jti"]}, claims


def _actor(db, actor):
    user = validate_application_login({"sub": str(actor["user_id"]), "sid": actor["sid"],
        "token_version": actor["token_version"], "jti": actor["jti"]}, db)
    if user.subject_id != actor["subject_id"]: raise HTTPException(401, "User subject changed")
    return ApplicationPrincipal(kind="user", user_id=user.id, subject_id=user.subject_id, is_admin=user.role == "admin")


def _binding(db, app, prepared):
    return {"incarnation": app.authority_incarnation, "epoch": app.authority_epoch,
        "instance_id": app.instance_id, "package_id": app.module_package_id,
        "artifact_sha256": prepared.package.sha256, "built_ui_sha256": prepared.built_ui_sha256,
        "configuration_sha256": hashlib.sha256(json.dumps(app.configuration or {}, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        "guard": read_authority_guard(db).generation}


def _admit(manager, db, key, installation_id, prepared, data):
    app = db.get(Installation, installation_id, populate_existing=True)
    if (app is None or not app.enabled or app.status != "active" or app.authority_mode != "enforced"
            or app.module_package_id != prepared.pin.module_package_id
            or _binding(db, app, prepared) != data["binding"]):
        raise ValueError("Delegation application changed")
    grant = manager._require_current_grant(db, key, installation_id, prepared)
    if (grant["revision"] != data["grant_record_revision"]
            or grant["data"]["grant_revision"] != data["grant_revision"]):
        raise ValueError("Delegation service authority changed")
    manager._require_ui_trust_in_snapshot(db, key, installation_id, prepared.built_ui_sha256, prepared)
    principal = _actor(db, data["actor"])
    definition = prepared.package.application_extension
    route = next((r for r in definition.routes if r.entrypoint_id == data["entrypoint_id"]), None)
    operation = find_operation(definition, data["operation_id"])
    permissions = application_permission_ids(db, installation_id, principal.user_id) & frozenset(
        p.permission_id for p in definition.permissions) & frozenset(data["permission_ids"])
    if (route is None or route.audience != "operator" or operation.operation_id not in route.delegated_operations
            or operation.kind not in {"query", "command"} or operation.timeout_seconds > 10
            or definition.storage.relational is not None
            or not can_access_application_route(route, principal, module_id=app.module_id, permission_ids=permissions)
            or not can_access_application_operation(operation, principal, audience="operator", permission_ids=permissions)):
        raise ValueError("Delegation human permission is unavailable")
    validate_operation_payload(data["payload"], operation.input_schema)
    return app, principal, operation, permissions


def _expired(data):
    boot, instant = authority._clock()
    return boot != data["boot_id"] or instant < data["issued_ms"] or instant >= data["expires_ms"]


def _receipt(value):
    data = value["data"]
    state, error = value["state"], data.get("error_code")
    if state == "pending" and _expired(data): state, error = "expired", "expired"
    if state == "running" and data.get("executor_generation") != process_generation(os.getpid(), os.geteuid()):
        state, error = "unknown", "execution_unconfirmed"
    return DelegationReceiptV1(delegation_id=value["record_id"], module_id=data["module_id"],
        operation_id=data["operation_id"], status=state,
        initiator={"kind": "user", "user_id": data["actor"]["user_id"], "subject_id": data["actor"]["subject_id"]}, executor=data["executor"],
        expires_at=datetime.fromisoformat(data["expires_at"]),
        result=data.get("result") if state == "succeeded" else None, error_code=error).model_dump(mode="json")


def _load(db, manager, key, installation_id, delegation_id):
    authority._identifier(delegation_id)
    row = db.get(Action, delegation_id, populate_existing=True)
    if row is None: raise HTTPException(404, "Delegation was not found")
    value = authority._load(db, key, KIND, row, delegation_id)
    if value["installation_id"] != installation_id:
        raise ValueError("Delegation belongs to another application")
    return row, value


def _audit(db, user_id, module_id, delegation_id, state):
    db.add(AuditLog(user_id=user_id if db.get(User, user_id) is not None else None, action="APPLICATION_DELEGATION_" + state.upper(),
        entity_type="application_extension", entity_name=module_id,
        changes={"delegation_id": delegation_id, "state": state}))


def create_delegation(engine, installation_id, binding, authorization, request):
    request = DelegationCreateV1.model_validate(request)
    manager = authority.configured_manager(engine)
    prepared = manager._prepare(installation_id)
    with Session(engine) as db:
        actor, claims = login_actor(db, authorization)
        session = db.get(UserSession, actor["sid"])
        session_expiry = session.expires_at
        if session_expiry is None: raise HTTPException(401, "A finite login is required")
        if session_expiry.tzinfo is None: session_expiry = session_expiry.replace(tzinfo=UTC)
        expires = min(datetime.now(UTC) + timedelta(seconds=request.ttl_seconds), session_expiry,
            datetime.fromtimestamp(claims["exp"], UTC))
    with manager.keys.locked() as key, Session(engine) as db, authority_transaction(db) as mutation:
        actor, _ = login_actor(db, authorization)
        app = db.get(Installation, installation_id, populate_existing=True)
        if app is None: raise ValueError("Application is unavailable")
        mutation.lock_application(read_application_authority(db, installation_id))
        if (binding["artifact_sha256"] != prepared.package.sha256
                or binding.get("built_ui_sha256") != prepared.built_ui_sha256):
            raise ValueError("Delegation UI binding changed")
        data = {"actor": actor, "module_id": app.module_id, "binding": _binding(db, app, prepared),
            "entrypoint_id": binding["entrypoint_id"], "operation_id": request.operation_id,
            "payload": request.payload, "permission_ids": sorted(application_permission_ids(db, app.id, actor["user_id"])
                & frozenset(p.permission_id for p in prepared.package.application_extension.permissions)),
            "executor": OperationExecutorV1(module_id=app.module_id, instance_id=app.instance_id,
                artifact_sha256=prepared.package.sha256).model_dump(mode="json")}
        grant = manager._require_current_grant(db, key, app.id, prepared)
        data.update(grant_revision=grant["data"]["grant_revision"], grant_record_revision=grant["revision"])
        _app, _principal, operation, _permissions = _admit(manager, db, key, app.id, prepared, data)
        fingerprint = digest({"actor": actor, "binding": binding, "request": request.model_dump(mode="json")})
        previous = db.get(Action, request.request_id)
        if previous is not None:
            _, previous_value = _load(db, manager, key, app.id, request.request_id)
            if previous_value["data"]["request_hash"] != fingerprint:
                raise ValueError("Delegation request ID belongs to another request or actor")
            return _receipt(previous_value)
        # Only never-dispatched pending records can expire automatically. Running
        # and unknown records retain evidence and are never freed for a replay.
        pending = list(db.scalars(select(Action).where(Action.installation_id == app.id,
            func.json_extract(Action.payload, "$.kind") == KIND,
            func.json_extract(Action.payload, "$.state") == "pending")))
        for old_row in pending:
            old = authority._load(db, key, KIND, old_row, old_row.request_id)
            if _expired(old["data"]):
                old.update(state="expired", revision=authority.new_authority_generation())
                old["data"]["error_code"] = "expired"
                authority._save(db, key, KIND, old_row, old)
        if (db.scalar(select(func.count()).select_from(Action).where(Action.installation_id == app.id,
                func.json_extract(Action.payload, "$.kind") == KIND)) >= MAX_RECORDS
                or db.scalar(select(func.count()).select_from(Action).where(Action.installation_id == app.id,
                    func.json_extract(Action.payload, "$.kind") == KIND,
                    func.json_extract(Action.payload, "$.state").in_(("pending", "running")))) >= 8):
            raise ValueError("Delegation journal budget is full; preserve unresolved outcomes")
        boot, instant = authority._clock()
        seconds = (expires - datetime.now(UTC)).total_seconds()
        if seconds < operation.timeout_seconds + 5:
            raise ValueError("Delegation expiry is too short for this operation")
        data.update(request_hash=fingerprint, boot_id=boot, issued_ms=instant,
            expires_ms=instant + int(seconds * 1000), expires_at=expires.isoformat(), result=None, error_code=None)
        value = authority._envelope(KIND, request.request_id, app.id, "pending", data)
        authority._save(db, key, KIND, Action(request_id=request.request_id, installation_id=app.id), value)
        _audit(db, actor["user_id"], app.module_id, request.request_id, "pending")
        return _receipt(value)


def inspect_delegation(engine, installation_id, delegation_id, *, authorization=None, cancel=False):
    manager = authority.configured_manager(engine); prepared = manager._prepare(installation_id)
    with manager.keys.locked() as key, (Session(engine) if cancel else authority._read_snapshot(engine)) as db, (authority_transaction(db) if cancel else nullcontext()) as mutation:
        row, value = _load(db, manager, key, installation_id, delegation_id)
        data = value["data"]
        if authorization is not None and login_actor(db, authorization)[0] != data["actor"]:
            raise HTTPException(403, "Delegation belongs to another login")
        app, _, _, _ = _admit(manager, db, key, installation_id, prepared, data)
        if cancel:
            mutation.lock_application(read_application_authority(db, installation_id))
            if value["state"] != "pending": raise ValueError("Only a pending delegation can be cancelled")
            value.update(state="expired" if _expired(data) else "cancelled", revision=authority.new_authority_generation())
            data["error_code"] = "expired" if value["state"] == "expired" else None
            authority._save(db, key, KIND, row, value)
            _audit(db, data["actor"]["user_id"], app.module_id, delegation_id, value["state"])
        return _receipt(value)


def execute_delegation(engine, installation_id, delegation_id, *, transport_secret, settings):
    """One service-authenticated claim; never rerun running/terminal records."""
    if type(transport_secret) is not bytes or len(transport_secret) != 32:
        raise ValueError("Authenticated service transport is required")
    manager = authority.configured_manager(engine); prepared = manager._prepare(installation_id)
    with manager.keys.locked() as key, Session(engine) as db, db.begin():
        _, initial = _load(db, manager, key, installation_id, delegation_id)
        app, _, _, _ = _admit(manager, db, key, installation_id, prepared, initial["data"])
        if initial["state"] != "pending" or _expired(initial["data"]): return _receipt(initial)
        socket_path = app.socket_path
    # Feature/identity probe has no DB/key lease and executes no app operation.
    hello = ApplicationServiceClient(Path(socket_path), transport_secret, 2).invoke(
        "three_mm.delegation.info", {}, {"audience": "internal"})
    if (type(hello.get("operation_delegation_contract")) is not int
            or hello.get("operation_delegation_contract") != 1 or hello.get("module_id") != prepared.package.manifest.module_id
            or hello.get("instance_id") != initial["data"]["executor"]["instance_id"] or hello.get("artifact_sha256") != prepared.package.sha256
            or hello.get("configuration_sha256") != initial["data"]["binding"]["configuration_sha256"]
            or type(hello.get("pid")) is not int or type(hello.get("uid")) is not int):
        raise ValueError("The selected independent application host does not support operation delegation")
    peer = (hello["pid"], hello["uid"], process_generation(hello["pid"], hello["uid"]))
    with manager.keys.locked() as key, Session(engine) as db, authority_transaction(db) as mutation:
        row, value = _load(db, manager, key, installation_id, delegation_id)
        app, _, operation, _ = _admit(manager, db, key, installation_id, prepared, value["data"])
        mutation.lock_application(read_application_authority(db, installation_id))
        if value["state"] != "pending" or _expired(value["data"]): return _receipt(value)
        value.update(state="running", revision=authority.new_authority_generation())
        claim = value["revision"]
        value["data"]["executor_generation"] = process_generation(os.getpid(), os.geteuid())
        authority._save(db, key, KIND, row, value)
        _audit(db, value["data"]["actor"]["user_id"], app.module_id, delegation_id, "running")

    with Session(engine) as db:
        def admit():
            with manager.keys.locked() as key:
                _, current = _load(db, manager, key, installation_id, delegation_id)
                data = current["data"]
                if current["state"] != "running" or current["revision"] != claim or _expired(data):
                    raise ValueError("Delegation execution is no longer current")
                app, principal, operation, permissions = _admit(manager, db, key, installation_id, prepared, data)
                delegation = OperationDelegationV1(delegation_id=delegation_id, operation_id=operation.operation_id,
                    required_permission=operation.required_permission, payload_sha256=digest(data["payload"]),
                    initiator={"kind": "user", "user_id": principal.user_id, "subject_id": principal.subject_id}, executor=data["executor"],
                    expires_at=datetime.fromisoformat(data["expires_at"]))
                context = {"audience": "operator", "user_id": principal.user_id, "platform_administrator": False,
                    "subject_id": principal.subject_id,
                    "permission_ids": sorted(permissions), "correlation_id": "delegation:" + delegation_id,
                    "idempotency_key": delegation_id if operation.kind == "command" else None,
                    "executor": data["executor"], "delegation": delegation.model_dump(mode="json")}
                package = db.get(ModulePackage, app.module_package_id)
                return InvocationSpec(app, package, operation.operation_id, data["payload"], context, "operator", peer)
        try:
            result = bounded_object(asyncio.run(invoke_with_relay(db, settings, admit)), limit=32_768)
            outcome, error = "succeeded", None
        except Exception:
            # Dispatch may have committed an effect. Never infer rollback or retry.
            result, outcome, error = None, "unknown", "execution_unconfirmed"
    with manager.keys.locked() as key, Session(engine) as db, authority_transaction(db):
        row, value = _load(db, manager, key, installation_id, delegation_id)
        if value["state"] != "running" or value["revision"] != claim:
            raise ValueError("Delegation completion changed; do not replay")
        if outcome == "succeeded":
            try:
                _admit(manager, db, key, installation_id, prepared, value["data"])
                if _expired(value["data"]): raise ValueError("Delegation expired")
            except (ValueError, HTTPException, authority.AuthorityManagementError):
                result, outcome, error = None, "unknown", "execution_unconfirmed"
        value.update(state=outcome, revision=authority.new_authority_generation())
        value["data"].update(result=result, error_code=error)
        authority._save(db, key, KIND, row, value)
        _audit(db, value["data"]["actor"]["user_id"], value["data"]["module_id"], delegation_id, outcome)
        return _receipt(value)
