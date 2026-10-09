"""Short DB-only authority writes for the common device platform, not Fleet."""

from contextlib import contextmanager

from sqlalchemy import select

from backend.db.device import Device, DeviceCredential, DevicePlatformState
from backend.services.authority_metadata import (
    AuthorityMetadataError, authority_transaction, read_device_control,
)
from three_mm_protocol.transport import DeviceProtocolError


def require_device_authority_session(db):
    """Check before any preflight SELECT can autoflush caller-owned work."""
    transaction = db.get_transaction()
    if (
        db.new or db.dirty or db.deleted or db.in_nested_transaction()
        or (transaction is not None and transaction.origin.name != "AUTOBEGIN")
    ):
        raise AuthorityMetadataError()


@contextmanager
def device_authority_write(db, device, *, credential_id=None):
    """Own one guard-first commit; re-read device ownership and optional principal.

    Only known read-only authentication/preflight AUTOBEGIN may be ended here.
    Pending ORM work, explicit transactions and savepoints are never discarded.
    This is not an adapter for arbitrary already-flushed SQL writes. Trusted
    internal/admin writers omit credential_id; device adapters must pass the
    credential they actually authenticated, never a client-selected substitute.
    No lazy metadata initialization or filesystem/network work in this scope.
    """
    require_device_authority_session(db)
    device_pk, device_id = device.id, device.device_id
    db.rollback()
    with authority_transaction(db) as mutation:
        current = db.scalar(
            select(Device)
            .where(Device.id == device_pk, Device.device_id == device_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if credential_id is not None:
            credential = db.scalar(select(DeviceCredential.id).where(
                DeviceCredential.device_id == device_pk,
                DeviceCredential.credential_id == credential_id,
                DeviceCredential.revoked_at.is_(None),
            ))
            if current is None or current.revoked_at is not None or credential is None:
                raise DeviceProtocolError("Authority credential is revoked", kind="unauthorized")
        if current is None or current.approved_at is None or current.revoked_at is not None:
            raise AuthorityMetadataError()
        read_device_control(db, current.id)
        platform = db.get(DevicePlatformState, current.id, populate_existing=True)
        if platform.authority_status != "bound" or platform.lifecycle == "revoked":
            raise AuthorityMetadataError()
        yield mutation, current
