"""Administrator configuration and operational status for application services."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.module import (
    ApplicationConnectorAttempt,
    ApplicationConnectorBinding,
    ApplicationEventCursor,
    ApplicationEventDelivery,
    ApplicationExtensionInstallation,
    ApplicationJobState,
    ApplicationSecretReference,
    ModulePackage,
)
from backend.db.user import User
from backend.services.application_connectors import (
    ApplicationConnectorError,
    bind_application_connector,
)
from backend.services.application_extensions import (
    ApplicationGatewayError,
    load_application_definition,
)
from backend.services.application_secrets import (
    ApplicationSecretError,
    create_secret_reference,
    rotate_secret_reference,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db
from three_mm_runtime.application_transport import (
    ApplicationServiceClient,
    ApplicationTransportError,
)


router = APIRouter(
    prefix="/api/v1/application-extensions",
    tags=["application-operations"],
)


class SecretCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    credential_kind: Literal["basic", "bearer", "api_key"]
    value: dict[str, str]
    model_config = ConfigDict(extra="forbid")


class SecretRotateRequest(BaseModel):
    value: dict[str, str]
    model_config = ConfigDict(extra="forbid")


class ConnectorBindingRequest(BaseModel):
    destination_origin: str = Field(min_length=8, max_length=512)
    secret_ref: str | None = Field(default=None, pattern=r"^secret_[0-9a-f]{32}$")
    model_config = ConfigDict(extra="forbid")


def _installation(db: Session, module_id: str) -> ApplicationExtensionInstallation:
    installation = db.scalar(
        select(ApplicationExtensionInstallation).where(
            ApplicationExtensionInstallation.module_id == module_id
        )
    )
    if installation is None:
        raise HTTPException(404, "Application extension was not found")
    return installation


def _secret_response(reference: ApplicationSecretReference) -> dict[str, object]:
    return {
        "secret_ref": reference.secret_ref,
        "label": reference.label,
        "credential_kind": reference.credential_kind,
        "version": reference.version,
        "created_at": reference.created_at,
        "rotated_at": reference.rotated_at,
        "revoked": reference.revoked_at is not None,
    }


@router.get("/{module_id}/secrets")
def list_application_secrets(
    module_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    references = db.scalars(
        select(ApplicationSecretReference)
        .where(ApplicationSecretReference.application_installation_id == installation.id)
        .order_by(ApplicationSecretReference.created_at)
    )
    return {"items": [_secret_response(item) for item in references]}


@router.post("/{module_id}/secrets", status_code=201)
def create_application_secret(
    module_id: str,
    request: SecretCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    try:
        reference = create_secret_reference(
            db,
            installation_id=installation.id,
            label=request.label,
            credential_kind=request.credential_kind,
            value=request.value,
        )
    except ApplicationSecretError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(AuditLog(user_id=admin.id, action="APPLICATION_SECRET_CREATED", entity_type="application_extension", entity_name=module_id, changes={"secret_ref": reference.secret_ref, "credential_kind": reference.credential_kind}))
    db.commit()
    return _secret_response(reference)


@router.put("/{module_id}/secrets/{secret_ref}")
def rotate_application_secret(
    module_id: str,
    secret_ref: str,
    request: SecretRotateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    reference = db.scalar(select(ApplicationSecretReference).where(ApplicationSecretReference.application_installation_id == installation.id, ApplicationSecretReference.secret_ref == secret_ref))
    if reference is None:
        raise HTTPException(404, "Application credential was not found")
    try:
        rotate_secret_reference(db, reference, request.value)
    except ApplicationSecretError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(AuditLog(user_id=admin.id, action="APPLICATION_SECRET_ROTATED", entity_type="application_extension", entity_name=module_id, changes={"secret_ref": secret_ref, "version": reference.version}))
    db.commit()
    return _secret_response(reference)


@router.delete("/{module_id}/secrets/{secret_ref}")
def revoke_application_secret(
    module_id: str,
    secret_ref: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    reference = db.scalar(select(ApplicationSecretReference).where(ApplicationSecretReference.application_installation_id == installation.id, ApplicationSecretReference.secret_ref == secret_ref))
    if reference is None:
        raise HTTPException(404, "Application credential was not found")
    reference.revoked_at = datetime.now(UTC)
    db.add(AuditLog(user_id=admin.id, action="APPLICATION_SECRET_REVOKED", entity_type="application_extension", entity_name=module_id, changes={"secret_ref": secret_ref}))
    db.commit()
    return {"status": "revoked", "secret_ref": secret_ref}


@router.put("/{module_id}/connectors/{connector_id}")
def configure_application_connector(
    module_id: str,
    connector_id: str,
    request: ConnectorBindingRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    try:
        binding = bind_application_connector(db, installation, connector_id, request.destination_origin, request.secret_ref)
    except ApplicationConnectorError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(AuditLog(user_id=admin.id, action="APPLICATION_CONNECTOR_CONFIGURED", entity_type="application_extension", entity_name=module_id, changes={"connector_id": connector_id, "destination_origin": binding.destination_origin, "uses_credential": binding.secret_reference_id is not None}))
    db.commit()
    return {"connector_id": binding.connector_id, "destination_origin": binding.destination_origin, "enabled": binding.enabled, "uses_credential": binding.secret_reference_id is not None}


@router.get("/{module_id}/operational-status")
def application_operational_status(
    module_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = db.get(ModulePackage, installation.module_package_id)
    if package is None:
        raise HTTPException(409, "Active application package is unavailable")
    try:
        definition = load_application_definition(package)
    except ApplicationGatewayError as exc:
        raise HTTPException(409, str(exc)) from exc
    runtime_status: dict[str, object] = {"revision": None, "outbox": {}}
    settings = get_settings().applications
    try:
        secret = (settings.key_root / f"{installation.instance_id}.key").read_bytes()
        runtime_status = ApplicationServiceClient(
            Path(installation.socket_path), secret, 5
        ).invoke(
            "three_mm.platform.status",
            {},
            {"audience": "internal", "correlation_id": f"status:{installation.instance_id}"},
        )
    except (OSError, ApplicationTransportError):
        pass
    jobs = list(db.scalars(select(ApplicationJobState).where(ApplicationJobState.application_installation_id == installation.id).order_by(ApplicationJobState.job_id)))
    connectors = list(db.scalars(select(ApplicationConnectorBinding).where(ApplicationConnectorBinding.application_installation_id == installation.id).order_by(ApplicationConnectorBinding.connector_id)))
    event_counts = {status: count for status, count in db.execute(select(ApplicationEventDelivery.status, func.count(ApplicationEventDelivery.id)).where(ApplicationEventDelivery.application_installation_id == installation.id).group_by(ApplicationEventDelivery.status))}
    connector_counts = {outcome: count for outcome, count in db.execute(select(ApplicationConnectorAttempt.outcome, func.count(ApplicationConnectorAttempt.id)).where(ApplicationConnectorAttempt.application_installation_id == installation.id).group_by(ApplicationConnectorAttempt.outcome))}
    cursors = list(db.scalars(select(ApplicationEventCursor).where(ApplicationEventCursor.application_installation_id == installation.id).order_by(ApplicationEventCursor.subscription_id)))
    return {
        "module_id": module_id,
        "version": installation.active_version,
        "service": {"status": installation.status, "enabled": installation.enabled, "last_health_check": installation.health_checked_at},
        "storage": {"declared_revision": definition.storage.schema_revision, "runtime_revision": runtime_status.get("revision"), "backup_required": definition.storage.backup_required},
        "events": {"counts": event_counts, "cursors": [{"subscription_id": item.subscription_id, "last_event_id": item.last_event_id, "acknowledged_total": item.acknowledged_count, "dead_letter_total": item.dead_letter_count} for item in cursors]},
        "jobs": [{"job_id": item.job_id, "next_run_at": item.next_run_at, "lease_until": item.lease_until, "last_outcome": item.last_outcome, "last_completed_at": item.last_completed_at, "run_count": item.run_count} for item in jobs],
        "connectors": {"attempt_counts": connector_counts, "items": [{"connector_id": item.connector_id, "destination_origin": item.destination_origin, "enabled": item.enabled, "last_outcome": item.last_outcome, "last_http_status": item.last_http_status, "last_checked_at": item.last_checked_at, "last_error_category": item.last_error_category} for item in connectors]},
        "outbox": runtime_status.get("outbox", {}),
    }
