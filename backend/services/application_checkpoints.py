"""Own-installation checkpoints through current scoped authority and SQL CAS.

The existing SDK methods/result shape remain unchanged. A CAS conflict or lost
reply is not a replay receipt: callers must read current state, never auto-retry.
No caller path, owner or human administrator identity is accepted.
"""

import json
import math
import re

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.module import ApplicationSyncCheckpoint as Checkpoint
from backend.services.application_authority_management import (
    effect_admission,
    lock_compatibility_admission,
)


CHECKPOINT_ID = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
MAX_VALUE_BYTES = 256 * 1024
MAX_REVISION = 2**53 - 1
_TRANSPORT_FIELDS = {
    "version",
    "request_id",
    "timestamp",
    "instance_id",
    "action",
    "signature",
}


def _plain_json(value, *, depth=0, budget=None):
    """Finite, bounded JSON, without a new schema for application values."""
    if budget is None:
        budget = [16384]
    budget[0] -= 1
    if budget[0] < 0 or depth > 16:
        raise ValueError("Checkpoint value structure exceeds limits")
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("Checkpoint value keys must be strings")
            _plain_json(key, depth=depth + 1, budget=budget)
            _plain_json(item, depth=depth + 1, budget=budget)
    elif type(value) is list:
        for item in value:
            _plain_json(item, depth=depth + 1, budget=budget)
    elif type(value) is str:
        value.encode("utf-8")  # Refuse unpaired surrogates.
    elif value is None or type(value) is bool:
        pass
    elif type(value) is int:
        if abs(value) > MAX_REVISION:
            raise ValueError("Checkpoint integer exceeds limits")
    elif type(value) is float:
        if not math.isfinite(value) or abs(value) > MAX_REVISION:
            raise ValueError("Checkpoint number is invalid")
    else:
        raise ValueError("Checkpoint value is not plain JSON")


def _bounded_value(value, limit):
    if type(value) is not dict:
        raise ValueError("Checkpoint value must be an object")
    try:
        _plain_json(value)
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("Checkpoint value is invalid") from None
    if len(encoded) > limit:
        raise ValueError("Checkpoint value exceeds its declared limit")


def _put(db, installation_id, checkpoint_id, expected_revision, value):
    # Compare AND mutate in one SQL statement, not a stale ORM read/assignment.
    changed = db.execute(
        update(Checkpoint)
        .where(
            Checkpoint.application_installation_id == installation_id,
            Checkpoint.checkpoint_id == checkpoint_id,
            Checkpoint.revision == expected_revision,
        )
        .values(revision=expected_revision + 1, value=value)
        .execution_options(synchronize_session=False)
    ).rowcount
    if changed not in (0, 1):
        raise ValueError("Checkpoint revision conflict")
    if changed == 0:
        if expected_revision != 0:
            raise ValueError("Checkpoint revision conflict")
        db.add(
            Checkpoint(
                application_installation_id=installation_id,
                checkpoint_id=checkpoint_id,
                revision=1,
                value=value,
            )
        )
        try:
            db.flush()  # The existing owner/ID unique constraint fences creates.
        except IntegrityError:
            raise ValueError("Checkpoint revision conflict") from None
    return {
        "checkpoint_id": checkpoint_id,
        "revision": expected_revision + 1,
        "value": value,
    }


def execute_checkpoint(db, installation, request):
    """Called only by the authenticated signed platform dispatcher."""
    action, checkpoint_id = request.get("action"), request.get("checkpoint_id")
    if action not in {"checkpoint.get", "checkpoint.put"}:
        raise ValueError("Platform action is unsupported")
    if type(checkpoint_id) is not str or not CHECKPOINT_ID.fullmatch(checkpoint_id):
        raise ValueError("Checkpoint identity is invalid")
    writing = action == "checkpoint.put"
    expected, value = request.get("expected_revision"), request.get("value")
    if writing and (
        type(expected) is not int or expected < 0 or type(value) is not dict
    ):
        raise ValueError("Checkpoint update is invalid")
    installation_id = installation.id
    if db.new or db.dirty or db.deleted or db.in_nested_transaction():
        raise ValueError("Checkpoint admission requires a clean session")
    # End the gateway's read transaction before key -> authority guard order.
    db.rollback()
    scope = f"checkpoint:{checkpoint_id}:" + ("write" if writing else "read")
    try:
        with effect_admission(db, installation_id, scope) as admission:
            if admission.compatibility:
                current = db.get(Installation, installation_id, populate_existing=True)
                if current is None:
                    raise ValueError("Application installation is not active")
                # Also linearize legacy reads/writes against disable/adoption.
                lock_compatibility_admission(db, current, required=True)
                if writing and len(json.dumps(value)) > MAX_VALUE_BYTES:
                    raise ValueError("Checkpoint update is invalid")
            else:
                fields = _TRANSPORT_FIELDS | {"checkpoint_id"}
                if writing:
                    fields |= {"expected_revision", "value"}
                if (
                    set(request) != fields
                    or type(request.get("version")) is not int
                    or request["version"] != 1
                ):
                    raise ValueError("Checkpoint request fields are invalid")
                declaration = next(
                    (
                        item
                        for item in admission.definition.checkpoints
                        if item.checkpoint_id == checkpoint_id
                    ),
                    None,
                )
                if declaration is None or writing and declaration.mode != "read_write":
                    raise ValueError("Checkpoint operation is not declared")
                if writing:
                    if expected >= MAX_REVISION:
                        raise ValueError("Checkpoint revision exceeds limits")
                    _bounded_value(value, declaration.max_value_bytes)
            if writing:
                result = _put(db, installation_id, checkpoint_id, expected, value)
                if not admission.compatibility:
                    admission.record_checkpoint_write(
                        checkpoint_id, expected, result["revision"]
                    )
            else:
                row = db.execute(
                    select(Checkpoint.revision, Checkpoint.value).where(
                        Checkpoint.application_installation_id == installation_id,
                        Checkpoint.checkpoint_id == checkpoint_id,
                    )
                ).one_or_none()
                result = {
                    "checkpoint_id": checkpoint_id,
                    "revision": row.revision if row else 0,
                    "value": row.value if row else {},
                }
                if not admission.compatibility:
                    if (
                        type(result["revision"]) is not int
                        or not 0 <= result["revision"] <= MAX_REVISION
                    ):
                        raise ValueError("Checkpoint revision is invalid")
                    if row is not None:
                        _bounded_value(result["value"], declaration.max_value_bytes)
            db.commit()  # Lease spans durable data/audit, never network I/O.
            admission()
            return result
    except Exception:
        db.rollback()
        raise
