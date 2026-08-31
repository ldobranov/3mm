"""Lifecycle, authorization and operation gateway for application extensions."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
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
    ApplicationKioskEnrollment,
    ApplicationKioskTerminal,
    ApplicationPermissionGrant,
    ApplicationSecretReference,
    ApplicationSyncCheckpoint,
    ModulePackage,
)
from backend.db.user import User
from backend.services.application_extensions import (
    ApplicationGatewayError,
    find_operation,
    invoke_application,
    load_application_definition,
)
from backend.services.application_access import application_permission_ids
from backend.utils.auth_dep import require_admin, require_user
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from three_mm_runtime.update_helper_client import UpdateHelperClient, UpdateHelperError
from three_mm_runtime.application_activation import application_instance_id


router = APIRouter(
    prefix="/api/v1/application-extensions",
    tags=["application-extensions"],
)


class ApplicationInstallationResponse(BaseModel):
    module_id: str
    active_version: str | None
    instance_id: str
    status: str
    enabled: bool
    error: str | None

    model_config = ConfigDict(from_attributes=True)


class ApplicationOperationRequest(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)

    model_config = ConfigDict(extra="forbid")


class ApplicationPermissionGrantRequest(BaseModel):
    user_id: int = Field(gt=0)
    permission_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=96)

    model_config = ConfigDict(extra="forbid")


class KioskEnrollmentRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    expires_in_minutes: int = Field(default=15, ge=1, le=1440)

    model_config = ConfigDict(extra="forbid")


class KioskEnrollmentClaim(BaseModel):
    code: str = Field(min_length=16, max_length=128)

    model_config = ConfigDict(extra="forbid")


class KioskSessionRequest(BaseModel):
    terminal_id: str = Field(min_length=16, max_length=64)
    credential: str = Field(min_length=32, max_length=160)

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


def _active_package(
    db: Session,
    installation: ApplicationExtensionInstallation,
) -> ModulePackage:
    if not installation.enabled or installation.status != "active":
        raise HTTPException(409, "Application extension is not active")
    package = db.get(ModulePackage, installation.module_package_id)
    if package is None:
        raise HTTPException(409, "Active application package is unavailable")
    return package


def _definition(package: ModulePackage):
    try:
        return load_application_definition(package)
    except ApplicationGatewayError as exc:
        raise HTTPException(409, str(exc)) from exc


def _user_from_claims(db: Session, claims: dict) -> User:
    subject = claims.get("sub") or claims.get("user_id")
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "User token subject is invalid") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "User is unavailable")
    return user


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


def _kiosk_token(module_id: str, terminal_id: str) -> str:
    return create_access_token(
        subject=f"kiosk:{terminal_id}",
        extra_claims={
            "token_type": "application_kiosk",
            "module_id": module_id,
            "terminal_id": terminal_id,
        },
        expires_delta=timedelta(minutes=15),
    )


def _invoke(
    installation: ApplicationExtensionInstallation,
    package: ModulePackage,
    operation_id: str,
    request: ApplicationOperationRequest,
    context: dict[str, object],
    audience: str,
) -> dict[str, object]:
    try:
        return invoke_application(
            installation,
            package,
            get_settings().applications,
            operation_id,
            request.payload,
            context,
            required_audience=audience,
        )
    except ApplicationGatewayError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("", response_model=list[ApplicationInstallationResponse])
def list_application_extensions(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return list(
        db.scalars(
            select(ApplicationExtensionInstallation).order_by(
                ApplicationExtensionInstallation.module_id
            )
        )
    )


@router.post("/packages/{sha256}/activate", response_model=ApplicationInstallationResponse)
def activate_application_extension(
    sha256: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None:
        raise HTTPException(404, "Application package was not found")
    try:
        definition = _definition(package)
    except ApplicationGatewayError as exc:
        raise HTTPException(409, str(exc)) from exc
    installation = db.scalar(
        select(ApplicationExtensionInstallation).where(
            ApplicationExtensionInstallation.module_id == package.module_id
        )
    )
    if installation is None:
        installation = ApplicationExtensionInstallation(
            module_id=package.module_id,
            module_package_id=package.id,
            instance_id=application_instance_id(package.module_id),
            socket_path="pending",
            status="activating",
            enabled=False,
        )
        db.add(installation)
    previous_package_id = (
        installation.module_package_id if installation.enabled else None
    )
    installation.previous_package_id = previous_package_id
    installation.module_package_id = package.id
    installation.status = "activating"
    installation.error = None
    db.commit()
    try:
        result = UpdateHelperClient(
            get_settings().applications.helper_socket,
            timeout_seconds=definition.service.startup_timeout_seconds + 10,
        ).activate_application_extension(sha256, admin.id)
        if result.get("module_id") != package.module_id or result.get("version") != package.version:
            raise UpdateHelperError("Application helper returned another package identity")
        installation.instance_id = str(result["instance_id"])
        installation.socket_path = str(result["socket_path"])
        installation.active_version = package.version
        installation.status = "active"
        installation.enabled = True
        installation.activated_at = datetime.now(UTC)
        installation.health_checked_at = datetime.now(UTC)
        installation.error = None
    except (KeyError, UpdateHelperError) as exc:
        installation.module_package_id = previous_package_id or package.id
        installation.status = "active" if previous_package_id else "failed"
        installation.enabled = previous_package_id is not None
        installation.error = str(exc)
        db.commit()
        raise HTTPException(409, "Application extension activation failed") from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="APPLICATION_EXTENSION_ACTIVATED",
            entity_type="application_extension",
            entity_name=package.module_id,
            changes={"version": package.version, "sha256": package.sha256},
        )
    )
    db.commit()
    db.refresh(installation)
    return installation


@router.post("/{module_id}/disable", response_model=ApplicationInstallationResponse)
def disable_application_extension(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    try:
        UpdateHelperClient(
            get_settings().applications.helper_socket
        ).disable_application_extension(installation.instance_id, admin.id)
    except UpdateHelperError as exc:
        raise HTTPException(409, "Application extension could not be disabled") from exc
    installation.enabled = False
    installation.status = "disabled"
    installation.error = None
    db.add(
        AuditLog(
            user_id=admin.id,
            action="APPLICATION_EXTENSION_DISABLED",
            entity_type="application_extension",
            entity_name=module_id,
            changes={"version": installation.active_version},
        )
    )
    db.commit()
    db.refresh(installation)
    return installation


@router.delete("/{module_id}")
def uninstall_application_extension(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    version = installation.active_version
    try:
        UpdateHelperClient(
            get_settings().applications.helper_socket
        ).uninstall_application_extension(installation.instance_id, admin.id)
    except UpdateHelperError as exc:
        raise HTTPException(409, "Application extension could not be uninstalled") from exc

    owned_models = (
        ApplicationConnectorAttempt,
        ApplicationConnectorBinding,
        ApplicationEventCursor,
        ApplicationEventDelivery,
        ApplicationJobState,
        ApplicationKioskTerminal,
        ApplicationKioskEnrollment,
        ApplicationPermissionGrant,
        ApplicationSecretReference,
        ApplicationSyncCheckpoint,
    )
    for model in owned_models:
        db.execute(
            delete(model).where(
                model.application_installation_id == installation.id
            )
        )
    db.delete(installation)
    db.add(
        AuditLog(
            user_id=admin.id,
            action="APPLICATION_EXTENSION_UNINSTALLED",
            entity_type="application_extension",
            entity_name=module_id,
            changes={"version": version, "data_preserved": True},
        )
    )
    db.commit()
    return {
        "status": "uninstalled",
        "module_id": module_id,
        "version": version,
        "data_preserved": True,
    }


@router.delete("/{module_id}/data")
def erase_application_extension_data(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.scalar(
        select(ApplicationExtensionInstallation.id).where(
            ApplicationExtensionInstallation.module_id == module_id
        )
    ) is not None:
        raise HTTPException(409, "Uninstall the application extension before erasing data")
    packages = list(
        db.scalars(select(ModulePackage).where(ModulePackage.module_id == module_id))
    )
    if not any(
        (package.manifest.get("entrypoints") or {}).get("core")
        == "application-extension.json"
        for package in packages
    ):
        raise HTTPException(404, "Application extension package was not found")

    try:
        UpdateHelperClient(
            get_settings().applications.helper_socket
        ).erase_application_extension_data(application_instance_id(module_id), admin.id)
    except UpdateHelperError as exc:
        raise HTTPException(409, "Application extension data could not be erased") from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="APPLICATION_EXTENSION_DATA_ERASED",
            entity_type="application_extension",
            entity_name=module_id,
            changes={"data_preserved": False},
        )
    )
    db.commit()
    return {"status": "erased", "module_id": module_id}


@router.post("/{module_id}/operations/{operation_id}")
def invoke_admin_operation(
    module_id: str,
    operation_id: str,
    request: ApplicationOperationRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    return _invoke(
        installation,
        package,
        operation_id,
        request,
        {
            "audience": "administrator",
            "correlation_id": uuid.uuid4().hex,
            "user_id": admin.id,
            "idempotency_key": request.idempotency_key,
        },
        "administrator",
    )


@router.post("/{module_id}/public/operations/{operation_id}")
def invoke_public_operation(
    module_id: str,
    operation_id: str,
    request: ApplicationOperationRequest,
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    return _invoke(
        installation,
        package,
        operation_id,
        request,
        {
            "audience": "public",
            "correlation_id": uuid.uuid4().hex,
            "idempotency_key": request.idempotency_key,
        },
        "public",
    )


@router.post("/{module_id}/operator/operations/{operation_id}")
def invoke_operator_operation(
    module_id: str,
    operation_id: str,
    request: ApplicationOperationRequest,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = _user_from_claims(db, claims)
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    definition = _definition(package)
    try:
        operation = find_operation(definition, operation_id)
    except ApplicationGatewayError as exc:
        raise HTTPException(404, str(exc)) from exc
    if "operator" not in operation.audiences:
        raise HTTPException(403, "Operation is not available to operators")
    permission_ids = application_permission_ids(db, installation.id, user.id)
    if not user.role == "admin" and operation.required_permission not in permission_ids:
        raise HTTPException(403, "Application permission is required")
    return _invoke(
        installation,
        package,
        operation_id,
        request,
        {
            "audience": "operator",
            "correlation_id": uuid.uuid4().hex,
            "user_id": user.id,
            "permission_ids": sorted(permission_ids),
            "idempotency_key": request.idempotency_key,
        },
        "operator",
    )


@router.post("/{module_id}/kiosk/operations/{operation_id}")
def invoke_kiosk_operation(
    module_id: str,
    operation_id: str,
    request: ApplicationOperationRequest,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    from backend.services.application_access import resolve_application_principal

    principal = resolve_application_principal(authorization, db)
    if principal.kind != "kiosk" or principal.kiosk_module_id != module_id:
        raise HTTPException(403, "A kiosk session for this application is required")
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    terminal = db.scalar(
        select(ApplicationKioskTerminal).where(
            ApplicationKioskTerminal.terminal_id == principal.terminal_id
        )
    )
    if terminal is None:
        raise HTTPException(401, "Kiosk terminal is unavailable")
    terminal.last_seen_at = datetime.now(UTC)
    result = _invoke(
        installation,
        package,
        operation_id,
        request,
        {
            "audience": "kiosk",
            "correlation_id": uuid.uuid4().hex,
            "terminal_id": terminal.terminal_id,
            "idempotency_key": request.idempotency_key,
        },
        "kiosk",
    )
    db.commit()
    return result


@router.get("/{module_id}/permissions")
def list_application_permissions(
    module_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    definition = _definition(package)
    grants = list(
        db.scalars(
            select(ApplicationPermissionGrant).where(
                ApplicationPermissionGrant.application_installation_id
                == installation.id
            )
        )
    )
    return {
        "permissions": [item.model_dump(mode="json") for item in definition.permissions],
        "grants": [
            {
                "user_id": item.user_id,
                "permission_id": item.permission_id,
                "granted_by": item.granted_by,
            }
            for item in grants
        ],
    }


@router.post("/{module_id}/permissions/grants", status_code=201)
def grant_application_permission(
    module_id: str,
    request: ApplicationPermissionGrantRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    definition = _definition(package)
    if request.permission_id not in {item.permission_id for item in definition.permissions}:
        raise HTTPException(422, "Application permission is not declared")
    if db.get(User, request.user_id) is None:
        raise HTTPException(404, "User was not found")
    grant = ApplicationPermissionGrant(
        application_installation_id=installation.id,
        user_id=request.user_id,
        permission_id=request.permission_id,
        granted_by=admin.id,
    )
    db.add(grant)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Application permission is already granted")
    return {"status": "granted"}


@router.delete("/{module_id}/permissions/grants/{user_id}/{permission_id}")
def revoke_application_permission(
    module_id: str,
    user_id: int,
    permission_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    grant = db.scalar(
        select(ApplicationPermissionGrant).where(
            ApplicationPermissionGrant.application_installation_id == installation.id,
            ApplicationPermissionGrant.user_id == user_id,
            ApplicationPermissionGrant.permission_id == permission_id,
        )
    )
    if grant is None:
        raise HTTPException(404, "Application permission grant was not found")
    db.delete(grant)
    db.commit()
    return {"status": "revoked"}


@router.post("/{module_id}/kiosk/enrollments", status_code=201)
def create_kiosk_enrollment(
    module_id: str,
    request: KioskEnrollmentRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    definition = _definition(package)
    if not any(
        "kiosk" in operation.audiences for operation in definition.operations
    ) or not any(route.audience == "kiosk" for route in definition.routes):
        raise HTTPException(409, "Application does not declare a kiosk interface")
    code = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(minutes=request.expires_in_minutes)
    db.add(
        ApplicationKioskEnrollment(
            application_installation_id=installation.id,
            code_hash=_secret_hash(code),
            label=request.label.strip(),
            expires_at=expires_at,
            created_by=admin.id,
        )
    )
    db.commit()
    return {"code": code, "expires_at": expires_at.isoformat()}


@router.post("/{module_id}/kiosk/enrollments/claim")
def claim_kiosk_enrollment(
    module_id: str,
    request: KioskEnrollmentClaim,
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    _active_package(db, installation)
    enrollment = db.scalar(
        select(ApplicationKioskEnrollment).where(
            ApplicationKioskEnrollment.application_installation_id == installation.id,
            ApplicationKioskEnrollment.code_hash == _secret_hash(request.code),
        )
    )
    if (
        enrollment is None
        or enrollment.consumed_at is not None
        or _is_expired(enrollment.expires_at)
    ):
        raise HTTPException(400, "Kiosk enrollment code is invalid or expired")
    terminal_id = uuid.uuid4().hex
    credential = secrets.token_urlsafe(32)
    terminal = ApplicationKioskTerminal(
        terminal_id=terminal_id,
        enrollment_id=enrollment.id,
        application_installation_id=installation.id,
        label=enrollment.label,
        credential_hash=_secret_hash(credential),
        enabled=True,
    )
    enrollment.consumed_at = datetime.now(UTC)
    db.add(terminal)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Kiosk enrollment code was already claimed")
    return {
        "terminal_id": terminal_id,
        "credential": credential,
        "access_token": _kiosk_token(module_id, terminal_id),
        "expires_in_seconds": 900,
    }


@router.post("/{module_id}/kiosk/sessions")
def create_kiosk_session(
    module_id: str,
    request: KioskSessionRequest,
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    _active_package(db, installation)
    terminal = db.scalar(
        select(ApplicationKioskTerminal).where(
            ApplicationKioskTerminal.application_installation_id == installation.id,
            ApplicationKioskTerminal.terminal_id == request.terminal_id,
            ApplicationKioskTerminal.enabled.is_(True),
        )
    )
    if terminal is None or not secrets.compare_digest(
        terminal.credential_hash,
        _secret_hash(request.credential),
    ):
        raise HTTPException(401, "Kiosk credential is invalid")
    terminal.last_seen_at = datetime.now(UTC)
    db.commit()
    return {
        "access_token": _kiosk_token(module_id, terminal.terminal_id),
        "expires_in_seconds": 900,
    }


@router.get("/{module_id}/kiosk/terminals")
def list_kiosk_terminals(
    module_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    terminals = db.scalars(
        select(ApplicationKioskTerminal)
        .where(ApplicationKioskTerminal.application_installation_id == installation.id)
        .order_by(ApplicationKioskTerminal.created_at)
    )
    return {
        "items": [
            {
                "terminal_id": item.terminal_id,
                "label": item.label,
                "enabled": item.enabled,
                "created_at": item.created_at,
                "last_seen_at": item.last_seen_at,
                "revoked_at": item.revoked_at,
            }
            for item in terminals
        ]
    }


@router.delete("/{module_id}/kiosk/terminals/{terminal_id}")
def revoke_kiosk_terminal(
    module_id: str,
    terminal_id: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    terminal = db.scalar(
        select(ApplicationKioskTerminal).where(
            ApplicationKioskTerminal.application_installation_id == installation.id,
            ApplicationKioskTerminal.terminal_id == terminal_id,
        )
    )
    if terminal is None:
        raise HTTPException(404, "Kiosk terminal was not found")
    terminal.enabled = False
    terminal.revoked_at = datetime.now(UTC)
    db.commit()
    return {"status": "revoked"}


@router.post("/{module_id}/health")
def check_application_health(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    try:
        definition = _definition(package)
        result = invoke_application(
            installation,
            package,
            get_settings().applications,
            definition.service.health_operation_id,
            {},
            {"audience": "internal", "correlation_id": uuid.uuid4().hex},
            required_audience="internal",
        )
    except ApplicationGatewayError as exc:
        raise HTTPException(409, str(exc)) from exc
    installation.health_checked_at = datetime.now(UTC)
    db.commit()
    return result
