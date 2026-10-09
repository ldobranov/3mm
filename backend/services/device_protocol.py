"""Common device operations, independent of HTTP, polling and hardware runtime.

HTTP authenticates through the same credential function as future adapters.
Adapter-owned sessions/notification and event dispatch are outside this layer.
The existing queue, registry, state and application contracts remain authoritative.
"""

import hmac
from datetime import UTC, datetime

from sqlalchemy import select

from backend.db.device import (
    Device,
    DeviceCredential,
    DeviceHeartbeat,
    DeviceInventorySnapshot,
    DeviceState,
    DeviceEvent,
    DeviceCapabilityState,
)
from backend.services.device_pairing import credential_secret_hash
from backend.services.authority_metadata import AuthorityMetadataError
from backend.services.node_enrollment import (
    enroll_node,
    EnrollmentConflict,
    EnrollmentCapacity,
)
from backend.services.device_commands import (
    deliver_next_command,
    command_envelope,
    record_command_result,
    DeviceCommandError,
    require_control_authority,
    _utc,
)
from backend.services.device_capability_registry import (
    has_registered_capability,
    replace_provider,
    provider_snapshot,
    CapabilityRegistryError,
    report_availability,
)
from backend.services.device_runtime_features import (
    replace_runtime_features,
    runtime_features_snapshot,
)
from three_mm_protocol import (
    DeviceDesiredState,
    CapabilityStateSnapshotV1,
    CoreNodeProtocolV1,
    IdentifierScanEventV1,
)
from three_mm_protocol.passage import PassageEventV1
from three_mm_protocol.node_security import CORE_DEVICE_AUDIT_EVENTS
from three_mm_protocol.transport import DeviceProtocolError


def authenticate_device(db, credential_id: str, secret: str) -> Device:
    if not credential_id or not secret or len(credential_id) + len(secret) > 1024:
        raise DeviceProtocolError("Invalid device credential", kind="unauthorized")
    credential = db.scalar(
        select(DeviceCredential)
        .where(DeviceCredential.credential_id == credential_id)
        .execution_options(populate_existing=True)
    )
    if credential is None or credential.revoked_at is not None:
        raise DeviceProtocolError("Invalid device credential", kind="unauthorized")
    device = db.scalar(
        select(Device)
        .where(Device.id == credential.device_id)
        .execution_options(populate_existing=True)
    )
    if (
        device is None
        or device.approved_at is None
        or device.revoked_at is not None
        or not hmac.compare_digest(
            credential.secret_hash, credential_secret_hash(secret)
        )
    ):
        raise DeviceProtocolError("Invalid device credential", kind="unauthorized")
    credential.last_used_at = datetime.now(UTC)
    db.commit()
    return device


def enroll(db, payload):
    try:
        return enroll_node(db, payload)
    except EnrollmentConflict as exc:
        raise DeviceProtocolError(
            "Enrollment conflict; administrator recovery required"
        ) from exc
    except EnrollmentCapacity as exc:
        raise DeviceProtocolError(
            "Enrollment capacity reached", kind="capacity"
        ) from exc


def state_row(db, device):
    row = db.scalar(select(DeviceState).where(DeviceState.device_id == device.id))
    if row is None:
        row = DeviceState(device_id=device.id, desired_state={}, reported_state={})
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def desired_snapshot(row, device_id):
    try:
        return DeviceDesiredState(
            device_id=device_id,
            revision=row.desired_revision,
            state=row.desired_state,
            updated_at=_utc(row.desired_updated_at),
        )
    except ValueError as exc:
        raise DeviceProtocolError(
            {
                "code": "stored_desired_state_invalid",
                "revision": row.desired_revision,
                "message": "Stored desired state requires a compatible bounded update; original data was preserved",
            }
        ) from exc


def capability_snapshot(device, row):
    return CapabilityStateSnapshotV1(
        device_id=device.device_id,
        capability_id=row.capability_id,
        values=row.values,
        observed_at=_utc(row.observed_at),
        received_at=_utc(row.received_at),
    )


class DeviceOperations:
    """Trusted adapter entry point, bound to its authenticated device principal.

    Create it after authenticate_device for EVERY incoming operation. Never retain
    credentials/principals as a substitute for revocation checks on a long-lived connection.
    """

    def __init__(self, db, device, *, credential_id=None):
        self.db, self.device = db, device
        self.credential_id = credential_id

    def own(self, device_id):
        if self.device.device_id != device_id:
            raise DeviceProtocolError("Device identity mismatch", kind="forbidden")

    def heartbeat(self, report):
        self.own(report.device_id)
        self.db.add(
            DeviceHeartbeat(
                device_id=self.device.id,
                protocol_version=report.protocol_version,
                payload=report.model_dump(mode="json"),
            )
        )
        self.db.commit()

    def inventory(self, report):
        self.own(report.device_id)
        self.db.add(
            DeviceInventorySnapshot(
                device_id=self.device.id, inventory=report.model_dump(mode="json")
            )
        )
        self.db.commit()

    def protocol(self):
        return CoreNodeProtocolV1(
            device_id=self.device.device_id,
            runtime_features_revision=runtime_features_snapshot(
                self.db, self.device
            ).revision,
            capability_registry_versions=(1, 2, 3),
            capability_provider_report_versions=(1, 2),
        )

    def features(self, report):
        self.own(report.device_id)
        self._require_credential_id()
        try:
            return replace_runtime_features(self.db, self.device, report,
                                            credential_id=self.credential_id)
        except DeviceProtocolError:
            raise  # Preserve authentication/ownership rejection, not HTTP 409.
        except ValueError as exc:
            self.db.rollback()
            raise DeviceProtocolError(str(exc)) from exc

    def provider(self, report):
        self.own(report.device_id)
        self._require_credential_id()
        try:
            row = replace_provider(self.db, self.device, report,
                                   credential_id=self.credential_id)
            snapshot = provider_snapshot(self.device, row)
            return snapshot
        except (CapabilityRegistryError, AuthorityMetadataError) as exc:
            self.db.rollback()
            raise DeviceProtocolError(str(exc)) from exc

    def _require_credential_id(self):
        if not self.credential_id:
            raise DeviceProtocolError("Authenticated device credential is required", kind="unauthorized")

    def next_command(self):
        try:
            command = deliver_next_command(self.db, device=self.device)
            return command_envelope(command, self.device.device_id) if command else None
        except (DeviceCommandError, AuthorityMetadataError) as exc:
            raise DeviceProtocolError(str(exc)) from exc

    def availability(self, report):
        self.own(report.device_id)
        try:
            row = report_availability(self.db, self.device, report)
            self.db.commit()
            return row
        except CapabilityRegistryError as exc:
            self.db.rollback()
            raise DeviceProtocolError(str(exc)) from exc

    def command_result(self, report):
        self.own(report.device_id)
        self._require_credential_id()
        try:
            command = record_command_result(self.db, device=self.device, result=report,
                                            credential_id=self.credential_id)
        except (DeviceCommandError, AuthorityMetadataError) as exc:
            raise DeviceProtocolError(str(exc)) from exc
        return command

    def authorize_execution(self, command_id):
        from backend.services.application_commands import authorize_execution

        try:
            require_control_authority(self.db, self.device)
            return authorize_execution(self.db, self.device, command_id)
        except (ValueError, DeviceCommandError) as exc:
            raise DeviceProtocolError(str(exc)) from exc

    def desired_state(self):
        try:
            require_control_authority(self.db, self.device)
        except DeviceCommandError as exc:
            raise DeviceProtocolError(str(exc)) from exc
        return desired_snapshot(state_row(self.db, self.device), self.device.device_id)

    def reported_state(self, report):
        self.own(report.device_id)
        row = state_row(self.db, self.device)
        if report.applied_revision > row.desired_revision:
            raise DeviceProtocolError("Reported revision is ahead of desired state")
        row.reported_revision, row.reported_state, row.reported_at = (
            report.applied_revision,
            report.state,
            report.reported_at,
        )
        self.db.commit()
        return report

    def capability_state(self, report):
        self.own(report.device_id)
        if not has_registered_capability(self.db, self.device, report.capability_id):
            raise DeviceProtocolError("Capability is not enabled on this device")
        row = self.db.scalar(
            select(DeviceCapabilityState).where(
                DeviceCapabilityState.device_id == self.device.id,
                DeviceCapabilityState.capability_id == report.capability_id,
            )
        )
        if row is None:
            row = DeviceCapabilityState(
                device_id=self.device.id,
                capability_id=report.capability_id,
                values=report.values,
                observed_at=report.observed_at,
                received_at=datetime.now(UTC),
            )
            self.db.add(row)
        elif report.observed_at >= _utc(row.observed_at):
            row.values, row.observed_at, row.received_at = (
                report.values,
                report.observed_at,
                datetime.now(UTC),
            )
        self.db.commit()
        self.db.refresh(row)
        return capability_snapshot(self.device, row)

    def event(self, report):
        self.own(report.device_id)
        if report.event_type in CORE_DEVICE_AUDIT_EVENTS:
            raise DeviceProtocolError(
                "Event type is reserved for Core audit", kind="forbidden"
            )
        if report.event_type == "identifier.scan.v1":
            IdentifierScanEventV1.model_validate(report.model_dump())
        if report.event_type == "access.passage.v1":
            PassageEventV1.model_validate(report.model_dump())
        existing = self.db.scalar(
            select(DeviceEvent).where(DeviceEvent.event_id == report.event_id)
        )
        if existing is not None and (
            existing.producer_kind != "device"
            or existing.device_id != self.device.id
            or existing.event_type != report.event_type
            or existing.payload != report.payload
            or _utc(existing.occurred_at) != _utc(report.occurred_at)
        ):
            raise DeviceProtocolError("Event identity has different content")
        if existing is None and report.event_type == "access.passage.v1":
            from backend.services.passage import validate_passage

            try:
                validate_passage(
                    self.db,
                    self.device,
                    PassageEventV1.model_validate(report.model_dump()),
                )
            except ValueError as exc:
                raise DeviceProtocolError(str(exc)) from exc
        event = existing or DeviceEvent(
            device_id=self.device.id,
            event_id=report.event_id,
            event_type=report.event_type,
            payload=report.payload,
            occurred_at=report.occurred_at,
        )
        if existing is None:
            self.db.add(event)
            self.db.commit()
            self.db.refresh(event)
        return event.id, existing is not None
