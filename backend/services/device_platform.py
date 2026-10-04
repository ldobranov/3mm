"""Generic installation-bound management and durable lifecycle operations.

Shared by Standalone/local Agent, Hub and extensions. No Fleet or hardware names.
"""

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, update
from backend.db.device import (
    Device,
    DeviceCredential,
    DevicePlatformState,
    DeviceHeartbeat,
    DeviceCommand,
    DeviceEvent,
)
from backend.services.installation_identity import _load_or_create
from backend.services.device_registry import as_utc, is_device_online
from backend.services.device_runtime_features import lock_device
from backend.services.device_protocol import DeviceOperations
from three_mm_protocol.device_platform import (
    AuthorityProofV1,
    DevicePlatformSnapshotV1,
    LifecycleReportV1,
    canonical_authority,
    validate_challenge_time,
)
from three_mm_protocol.transport import DeviceProtocolError


def sign_authority(db, request, payload):
    validate_challenge_time(request)
    identity, private = _load_or_create(db)
    validate_challenge_time(request)
    return AuthorityProofV1(
        identity=identity,
        request=request,
        payload=payload,
        signature=base64.b64encode(
            private.sign(canonical_authority(identity, request, payload))
        ).decode("ascii"),
    )


def identity_proof(db, request):
    if request.operation != "identity":
        raise DeviceProtocolError(
            "Anonymous proof cannot authorize device operations", kind="forbidden"
        )
    return sign_authority(db, request, {})


def _state(db, device):
    row = db.get(DevicePlatformState, device.id, populate_existing=True)
    if row is None:
        row = DevicePlatformState(
            device_id=device.id,
            authority_status="bound",
            lifecycle="active",
            revision=0,
        )
        db.add(row)
        db.flush()
    return row


def _effective_lifecycle(db, device, row):
    if row.authority_status == "released":
        return (
            "enrollment_pending" if row.lifecycle == "enrollment_pending" else "unowned"
        )
    active_credential = db.scalar(
        select(DeviceCredential.id).where(
            DeviceCredential.device_id == device.id,
            DeviceCredential.revoked_at.is_(None),
        )
    )
    any_credential = db.scalar(
        select(DeviceCredential.id).where(DeviceCredential.device_id == device.id)
    )
    return (
        "revoked"
        if device.revoked_at is not None
        or (any_credential is not None and active_credential is None)
        else row.lifecycle
    )


def platform_snapshot(db, device, *, now=None, offline_after=None):
    if offline_after is None:
        from backend.config import get_settings

        offline_after = timedelta(
            seconds=get_settings().backend.device_offline_after_seconds
        )
    # Initialize/decrypt identity before taking transactional device locks.
    identity, _ = _load_or_create(db)
    row = _state(db, device)
    latest = db.scalar(
        select(DeviceHeartbeat)
        .where(DeviceHeartbeat.device_id == device.id)
        .order_by(DeviceHeartbeat.received_at.desc())
        .limit(1)
    )
    last_seen = as_utc(latest.received_at) if latest else None
    return DevicePlatformSnapshotV1(
        device_id=device.device_id,
        installation=identity,
        authority_status=row.authority_status,
        lifecycle=_effective_lifecycle(db, device, row),
        revision=row.revision,
        reason=row.reason,
        last_seen_at=last_seen,
        connectivity=(
            "online"
            if is_device_online(
                last_seen_at=last_seen,
                now=now or datetime.now(UTC),
                offline_after=offline_after,
            )
            else "offline"
        ),
    )


def management_payload(db, device, request):
    validate_challenge_time(request)
    if request.device_id != device.device_id:
        raise DeviceProtocolError("Authority request device mismatch", kind="forbidden")
    credential = db.scalar(
        select(DeviceCredential).where(
            DeviceCredential.device_id == device.id,
            DeviceCredential.credential_id == request.credential_id,
            DeviceCredential.revoked_at.is_(None),
        )
    )
    if device.revoked_at is not None or credential is None:
        raise DeviceProtocolError(
            "Authority credential is revoked", kind="unauthorized"
        )
    operations = DeviceOperations(db, device)
    if request.operation == "command":
        command = operations.next_command()
        return {"command": command.model_dump(mode="json") if command else None}
    if request.operation == "desired_state":
        return operations.desired_state().model_dump(mode="json")
    if request.operation == "execution_permit":
        return operations.authorize_execution(request.command_id)
    if request.operation == "platform":
        return platform_snapshot(db, device).model_dump(mode="json")
    raise DeviceProtocolError("Unsupported authenticated authority operation")


def _audit(db, device, event_type, payload):
    db.add(
        DeviceEvent(
            device_id=device.id,
            event_id="evt_" + uuid4().hex,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(UTC),
        )
    )


def report_lifecycle(db, device, report):
    if report.device_id != device.device_id:
        raise DeviceProtocolError("Lifecycle device mismatch", kind="forbidden")
    _load_or_create(db)
    lock_device(db, device)
    db.refresh(device)
    row = _state(db, device)
    if row.authority_status != "bound" or _effective_lifecycle(db, device, row) in {
        "revoked",
        "unowned",
    }:
        raise DeviceProtocolError(
            "Revoked/released authority needs administrator recovery", kind="forbidden"
        )
    if (row.lifecycle, row.reason) == (
        report.lifecycle,
        report.reason,
    ) and report.expected_revision in {row.revision, row.revision - 1}:
        db.commit()
        return platform_snapshot(db, device)
    if report.expected_revision != row.revision or row.revision >= 2147483646:
        raise DeviceProtocolError("Lifecycle revision changed; read and retry")
    row.lifecycle, row.reason, row.revision, row.updated_at = (
        report.lifecycle,
        report.reason,
        row.revision + 1,
        datetime.now(UTC),
    )
    _audit(
        db,
        device,
        "device.lifecycle.updated",
        {"lifecycle": row.lifecycle, "revision": row.revision, "reason": row.reason},
    )
    db.commit()
    return platform_snapshot(db, device)


def release_authority(db, device, *, expected_revision, confirmed_device_id, actor_id):
    if confirmed_device_id != device.device_id:
        raise DeviceProtocolError("Explicit device identity confirmation is required")
    _load_or_create(db)
    lock_device(db, device)
    db.refresh(device)
    row = _state(db, device)
    if row.authority_status == "released" and expected_revision in {
        row.revision,
        row.revision - 1,
    }:
        return platform_snapshot(db, device)
    if expected_revision != row.revision or row.revision >= 2147483646:
        raise DeviceProtocolError("Authority revision changed; read and retry")
    now = datetime.now(UTC)
    device.revoked_at = now
    db.execute(
        update(DeviceCredential)
        .where(
            DeviceCredential.device_id == device.id,
            DeviceCredential.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    # Never call delivered/unconfirmed actions cancelled or replayable.
    db.execute(
        update(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status == "queued",
            DeviceCommand.delivered_at.is_(None),
            DeviceCommand.delivery_attempts == 0,
        )
        .values(
            status="failed",
            completed_at=now,
            result={"execution_state": "not_dispatched"},
            error="Installation authority released before dispatch",
        )
    )
    row.authority_status, row.lifecycle, row.reason = (
        "released",
        "unowned",
        "authority.released",
    )
    row.revision, row.updated_at = row.revision + 1, now
    _audit(
        db,
        device,
        "device.authority.released",
        {"revision": row.revision, "actor_id": actor_id},
    )
    db.commit()
    return platform_snapshot(db, device)


def prepare_reenrollment(
    db, device, *, expected_revision, confirmed_device_id, actor_id
):
    """Explicit administrator recovery; no credential/authority is granted here."""
    from backend.db.device import DevicePairingRequest

    if confirmed_device_id != device.device_id:
        raise DeviceProtocolError("Explicit device identity confirmation is required")
    _load_or_create(db)
    lock_device(db, device)
    row = _state(db, device)
    if (
        row.authority_status != "released"
        or expected_revision != row.revision
        or row.revision >= 2147483646
    ):
        raise DeviceProtocolError(
            "Release authority and read its revision before preparing enrollment"
        )
    # Retain old approvals as historical records, freeing only the active Node
    # enrollment index. Old tokens cannot complete or regain their credential.
    for previous in db.scalars(
        select(DevicePairingRequest).where(
            DevicePairingRequest.requested_device_id == device.device_id,
            DevicePairingRequest.created_by_user_id.is_(None),
        )
    ):
        previous.requested_metadata = {
            **previous.requested_metadata,
            "archived_device_id": device.device_id,
        }
        previous.requested_device_id = None
    row.lifecycle, row.reason = "enrollment_pending", "authority.enrollment_authorized"
    row.revision, row.updated_at = row.revision + 1, datetime.now(UTC)
    _audit(
        db,
        device,
        "device.authority.enrollment_prepared",
        {"revision": row.revision, "actor_id": actor_id},
    )
    db.commit()
    return platform_snapshot(db, device)
