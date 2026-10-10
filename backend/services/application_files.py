"""Current sealed file admission; target-owned execution, never Core file writes.

Only reviewed native headless applications are supported. The existing sealed
action journal records machine admissions/receipts, not a fabricated human audit
actor. No content, host path or transport secret is retained there. Uncertainty
is permanent until operator review: even an exact retry never redispatches a
mutation. Key/DB leases never span runtime IPC.
"""

from pathlib import Path
import re

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backend.db.application_authority_grant import ApplicationAuthorityAction as Action
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.services import application_authority_management as authority
from backend.services.application_authority_keys import AuthorityReviewKeyError
from backend.services.application_authority_sources import _core_identity
from backend.services.authority_metadata import (
    authority_transaction,
    read_application_authority,
)
from three_mm_application_sdk.file_wire import (
    file_receipt,
    file_request_identity,
    parse_file_request,
    validate_file_result,
)
from three_mm_application_sdk import ApplicationFileLimits
from three_mm_runtime.application_file_executor import call_file_executor


MAX_FILE_ACTIONS_PER_INSTALLATION = 4096


class ApplicationFileAuthorityError(ValueError):
    def __init__(self):
        super().__init__("Private file authority or runtime is unavailable")


def _clean_session(db):
    if db.new or db.dirty or db.deleted or db.in_nested_transaction():
        raise ApplicationFileAuthorityError()
    db.rollback()  # End the gateway's read transaction before key -> guard order.


def _principal(db, installation_id):
    current = read_application_authority(db, installation_id)
    return {
        "core_installation_id": _core_identity(db),
        "application_installation_id": str(installation_id),
        "incarnation": current.incarnation,
        "module_id": current.module_id,
    }


def _runtime(db, installation_id):
    row = db.get(Installation, installation_id, populate_existing=True)
    if row is None or not row.enabled or row.status != "active":
        raise ApplicationFileAuthorityError()
    instance, raw_path = row.instance_id, row.socket_path
    if (
        type(instance) is not str
        or not re.fullmatch(r"[0-9a-f]{24}", instance)
        or type(raw_path) is not str
    ):
        raise ApplicationFileAuthorityError()
    path = Path(raw_path)
    if (
        not path.is_absolute()
        or path.name != "service.sock"
        or path.parent.name != "run"
        or path.parent.parent.name != instance
        or ".." in path.parts
    ):
        raise ApplicationFileAuthorityError()
    return instance, path.with_name("files.sock")


def _journal(db, key, installation_id, request_id, request_hash=None):
    row = db.get(Action, request_id, populate_existing=True)
    if row is None:
        return None
    value = authority._load(db, key, "action", row, request_id)
    data = value["data"]
    if (
        row.installation_id != installation_id
        or data.get("operation") != "files_execute"
        or data.get("actor") != ["application", str(installation_id)]
        or data.get("principal") != _principal(db, installation_id)
        or request_hash is not None
        and data.get("request_hash") != request_hash
        or value["state"] not in {"execution_unconfirmed", "completed"}
        or data.get("result", {}).get("outcome") != value["state"]
    ):
        raise ApplicationFileAuthorityError()
    return value


def _historical(value):
    return {"receipt": dict(value["data"]["result"]), "historical": True}


def file_operation_status(db, installation, request_id):
    installation_id = installation.id
    try:
        request_id = authority._identifier(request_id)
        _clean_session(db)
        manager = authority.configured_manager(db.get_bind().engine)
        with manager.keys.locked() as key, authority_transaction(db):
            value = _journal(db, key, installation_id, request_id)
            return (
                {"status": "found", **_historical(value)}
                if value
                else {"status": "not_found"}
            )
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RuntimeError,
    ):
        db.rollback()
        raise ApplicationFileAuthorityError() from None


def execute_private_file(db, installation, request, *, transport_secret):
    """SDK gateway entry; identity/key come only from authenticated Core transport.

    The linearization point is the committed admission. An already admitted
    operation may finish after revocation; subsequent admissions are denied. A
    restart/rollback changes the runtime nonce; an old permit is never reused.
    """
    installation_id = installation.id
    try:
        request, content = parse_file_request(request)
        if type(transport_secret) is not bytes or len(transport_secret) != 32:
            raise ApplicationFileAuthorityError()
        writing = request["operation"] in {"put", "delete"}
        scope = "storage:private_files_" + ("write" if writing else "read")
        request_hash = file_request_identity(request)
        _clean_session(db)
        manager = authority.configured_manager(db.get_bind().engine)
        # Exact historical mutations can be inspected after revoke/disable. A
        # changed request, foreign owner, rotated key or recovery fence denies.
        with manager.keys.locked() as key, authority_transaction(db):
            existing = _journal(
                db, key, installation_id, request["request_id"], request_hash
            )
            if existing is not None:
                return _historical(existing)
            if read_application_authority(db, installation_id).mode != "enforced":
                raise ApplicationFileAuthorityError()
            runtime = _runtime(db, installation_id)
        prepared = manager._prepare(installation_id)  # Archive I/O outside leases.
        declaration = prepared[1].application_extension.storage.private_files
        if (
            declaration is None
            or content is not None
            and len(content) > declaration.max_file_bytes
        ):
            raise ApplicationFileAuthorityError()
        # Hello exposes no private content and opens no SDK namespace. Final
        # guard below rechecks the actual grant, resources and runtime binding.
        hello = call_file_executor(runtime[1], transport_secret, "hello", {})
        if (
            type(hello) is not dict
            or set(hello)
            != {
                "instance_id",
                "package_sha256",
                "runtime_nonce",
                "clock_ms",
                "declaration",
            }
            or hello["instance_id"] != runtime[0]
            or hello["package_sha256"] != prepared[0].sha256
            or type(hello["runtime_nonce"]) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", hello["runtime_nonce"])
            or type(hello["clock_ms"]) is not int
            or authority._canonical_bytes(hello["declaration"])
            != authority._canonical_bytes(declaration.model_dump(mode="json"))
        ):
            raise ApplicationFileAuthorityError()
        with manager.keys.locked() as key, authority_transaction(db) as mutation:
            existing = _journal(
                db, key, installation_id, request["request_id"], request_hash
            )
            if existing is not None:
                return _historical(existing)
            grant = manager._require_grant(db, key, installation_id, prepared, scope)
            if _runtime(db, installation_id) != runtime:
                raise ApplicationFileAuthorityError()
            current = read_application_authority(db, installation_id)
            mutation.lock_application(current)
            _, now = authority._clock()
            if not 0 <= now - hello["clock_ms"] <= 5000:
                raise ApplicationFileAuthorityError()
            admission = {
                "runtime_nonce": hello["runtime_nonce"],
                "instance_id": runtime[0],
                "package_sha256": prepared[0].sha256,
                "declaration": declaration.model_dump(mode="json"),
                "authority_epoch": current.epoch,
                "deadline_ms": now + 5000,
            }
            pending = file_receipt(request)
            if writing:
                count = db.scalar(
                    select(func.count())
                    .select_from(Action)
                    .where(Action.installation_id == installation_id)
                )
                if count >= MAX_FILE_ACTIONS_PER_INSTALLATION:
                    raise ApplicationFileAuthorityError()  # No eviction/replay of unknown receipts.
                data = {
                    "operation": "files_execute",
                    "actor": ["application", str(installation_id)],
                    "principal": _principal(db, installation_id),
                    "request_hash": request_hash,
                    "authority_epoch": current.epoch,
                    "grant_revision": grant["data"]["grant_revision"],
                    "plan_id": grant["data"]["plan_id"],
                    "native_review_id": grant["data"]["native_review_id"],
                    "artifact_sha256": prepared[0].sha256,
                    "runtime_nonce": hello["runtime_nonce"],
                    "result": pending,
                }
                authority._save(
                    db,
                    key,
                    "action",
                    Action(
                        request_id=request["request_id"],
                        installation_id=installation_id,
                    ),
                    authority._envelope(
                        "action",
                        request["request_id"],
                        installation_id,
                        "execution_unconfirmed",
                        data,
                    ),
                )
                mutation.advance_guard_revision()
        # COMMIT completed, key/guard released. Exactly one dispatch, no retries.
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RuntimeError,
    ):
        db.rollback()
        raise ApplicationFileAuthorityError() from None
    try:
        result = call_file_executor(
            runtime[1],
            transport_secret,
            "execute",
            {"admission": admission, "request": request},
        )
        validate_file_result(
            result,
            request,
            ApplicationFileLimits(
                declaration.max_file_bytes,
                declaration.max_total_bytes,
                declaration.max_files,
            ),
        )
        completed = file_receipt(request, result, outcome="completed")
        if writing:
            with manager.keys.locked() as key, authority_transaction(db) as mutation:
                value = _journal(
                    db, key, installation_id, request["request_id"], request_hash
                )
                if value is None or value["state"] != "execution_unconfirmed":
                    raise ApplicationFileAuthorityError()
                value["state"] = "completed"
                value["revision"] = authority.new_authority_generation()
                value["data"]["result"] = completed
                authority._save(
                    db, key, "action", db.get(Action, request["request_id"]), value
                )
                mutation.advance_guard_revision()
            return {"receipt": completed, "historical": False}
        return {"receipt": completed, "file_result": result, "historical": False}
    except (
        authority.AuthorityManagementError,
        AuthorityReviewKeyError,
        SQLAlchemyError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        OSError,
        RuntimeError,
    ):
        db.rollback()
        if writing:
            return {"receipt": pending, "historical": False}
        raise ApplicationFileAuthorityError() from None
