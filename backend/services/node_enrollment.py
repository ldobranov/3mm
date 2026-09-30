"""Bounded, idempotent Node requests; only the admin approval path grants rights."""
from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.device import Device, DeviceCredential, DevicePairingRequest
from backend.services.device_pairing import pairing_code_hash
from three_mm_protocol.fleet_pairing import NodeEnrollmentRequest, NodeEnrollmentResponse


class EnrollmentConflict(ValueError):
    pass


class EnrollmentCapacity(ValueError):
    pass


def enroll_node(db: Session, payload: NodeEnrollmentRequest, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Enrollment timestamps must include a timezone")
    token_hash = pairing_code_hash(payload.request_token)
    row = db.scalar(select(DevicePairingRequest).where(
        DevicePairingRequest.created_by_user_id.is_(None),
        DevicePairingRequest.requested_device_id == payload.device_id,
    ))
    if row is None:
        if db.scalar(select(Device.id).where(Device.device_id == payload.device_id)) is not None:
            raise EnrollmentConflict("Device already registered; administrator recovery required")
        count = db.scalar(select(func.count()).select_from(DevicePairingRequest).where(
            DevicePairingRequest.created_by_user_id.is_(None)))
        if count >= 1000:
            raise EnrollmentCapacity("Enrollment capacity reached")
        row = DevicePairingRequest(
            code_hash=token_hash, requested_device_id=payload.device_id,
            created_by_user_id=None, created_at=now, claimed_at=now,
            expires_at=now + timedelta(hours=24),
            requested_metadata={
                "enrollment_version": 1, "display_name": payload.display_name,
                "role": "node", "protocol_version": payload.protocol_version,
                "credential_id": payload.credential_id,
                "credential_secret_hash": payload.credential_secret_hash,
            },
        )
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # The request may have arrived twice while the first response was lost.
            row = db.scalar(select(DevicePairingRequest).where(
                DevicePairingRequest.created_by_user_id.is_(None),
                DevicePairingRequest.requested_device_id == payload.device_id,
            ))
            if row is None:
                raise EnrollmentConflict("Enrollment identity conflict")
    metadata = row.requested_metadata or {}
    if (not secrets.compare_digest(row.code_hash, token_hash)
            or metadata.get("enrollment_version") != 1
            or metadata.get("credential_id") != payload.credential_id
            or metadata.get("credential_secret_hash") != payload.credential_secret_hash):
        raise EnrollmentConflict("Enrollment identity conflict")
    if row.approved_at is not None:
        credential = db.scalar(select(DeviceCredential).join(Device).where(
            Device.id == row.device_id, Device.revoked_at.is_(None),
            DeviceCredential.credential_id == payload.credential_id,
            DeviceCredential.revoked_at.is_(None),
        ))
        state = "approved" if credential is not None else "revoked"
    elif metadata.get("rejected"):
        state = "rejected"
    elif (row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None
          else row.expires_at) <= now:
        state = "expired"
    else:
        state = "pending_approval"
    return NodeEnrollmentResponse(device_id=payload.device_id,
                                  credential_id=payload.credential_id, status=state)
