"""Lifecycle, authorization and operation gateway for application extensions."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.audit_log import AuditLog
from backend.db.device import Device
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
from backend.db.association_tables import role_application_grants
from backend.services.application_extensions import (
    ApplicationGatewayError,
    find_operation,
    invoke_application,
    load_application_definition,
)
from backend.services.application_public_web import (
    ApplicationPublicWebError,
    validate_public_http_candidate,
)
from backend.services.application_configuration import (
    ApplicationConfigurationError,
    device_configuration_keys,
    resolve_application_configuration,
)
from backend.services.application_access import (
    application_permission_ids, ApplicationPrincipal,
    can_access_application_route, can_access_application_operation,
)
from backend.services.application_commands import invalidate_commands
from backend.services.authority_metadata import (
    ApplicationAuthoritySnapshot,
    AuthorityMetadataError,
    authority_transaction,
    read_application_authority,
    read_authority_guard,
)
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


class ApplicationActivationRequest(BaseModel):
    configuration: dict[str, object] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class ApplicationAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module_id: str
    active_version: str
    user_id: int
    allowed_route_ids: list[str]
    allowed_operation_ids: list[str]


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


class ApplicationLifecycleRecoveryRequest(BaseModel):
    confirmed_external_outcome_reviewed: Literal[True]

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class _LifecycleTicket:
    application: ApplicationAuthoritySnapshot
    operation: str
    state: tuple
    guard_generation: str


def _helper_lifecycle(ticket):
    return {
        "installation_id": ticket.application.installation_id,
        "module_id": ticket.application.module_id,
        "instance_id": ticket.state[2],
        "incarnation": ticket.application.incarnation,
        "epoch": ticket.application.epoch,
        "guard_generation": ticket.guard_generation,
    }


def _lifecycle_state(installation):
    return (
        installation.module_package_id, installation.previous_package_id,
        installation.instance_id, installation.active_version,
        installation.status, installation.enabled, installation.socket_path,
        deepcopy(installation.configuration),
    )


def _package_state(package):
    return (
        package.id, package.module_id, package.version, package.sha256,
        package.file_path, deepcopy(package.manifest),
    )


@contextmanager
def _lifecycle_write(db, *, expected_guard=None):
    """Close this route's known read-only preflight; never span helper I/O."""
    try:
        if db.new or db.dirty or db.deleted:
            raise AuthorityMetadataError()
        db.rollback()
        with authority_transaction(db, expected_guard=expected_guard) as authority:
            yield authority
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc


def _lifecycle_audit(db, actor_id, module_id, action, **changes):
    db.add(AuditLog(
        user_id=actor_id, action=action, entity_type="application_extension",
        entity_name=module_id, changes=changes,
    ))


@contextmanager
def _activation_authority(db, expected, sha256, configuration, guard):
    if expected is None or expected.mode == 'compatibility':
        yield
        return
    from backend.services.application_authority_management import configured_manager, AuthorityManagementError
    from backend.services.application_authority_keys import AuthorityReviewKeyError
    try:
        with configured_manager(db.get_bind().engine).native_activation(
                expected.installation_id, sha256, configuration, guard):
            yield
    except (AuthorityManagementError, AuthorityReviewKeyError, ValueError):
        raise HTTPException(409, 'Reviewed native artifact authority is unavailable; staged activation is not supported') from None


def _start_lifecycle(db, authority, installation, operation, actor_id):
    current = authority.advance_application_epoch(
        read_application_authority(db, installation.id)
    )
    installation.status = operation
    installation.enabled = False
    installation.error = None
    invalidate_commands(db, installation.id)
    _lifecycle_audit(
        db, actor_id, installation.module_id, "APPLICATION_EXTENSION_LIFECYCLE_STARTED",
        operation=operation, version=installation.active_version,
    )
    db.flush()
    return _LifecycleTicket(current, operation, _lifecycle_state(installation), authority.guard.generation)


def _lock_lifecycle(db, authority, ticket):
    if authority.guard.generation != ticket.guard_generation:
        authority.reject()
    authority.lock_application(ticket.application, lifecycle_status=ticket.operation)
    installation = db.get(
        ApplicationExtensionInstallation, ticket.application.installation_id,
        populate_existing=True,
    )
    if installation is None or _lifecycle_state(installation) != ticket.state:
        authority.reject()
    authority.advance_application_epoch(ticket.application)
    return installation


def _lifecycle_failed(db, ticket, actor_id):
    # A helper timeout/rejection is not proof of filesystem/runtime rollback.
    # Do not retry the helper, restore old authority, or release unknown jobs.
    with _lifecycle_write(db) as authority:
        installation = _lock_lifecycle(db, authority, ticket)
        installation.status = "recovery_required"
        installation.enabled = False
        installation.error = "Application lifecycle outcome is unconfirmed; administrative recovery is required"
        _lifecycle_audit(
            db, actor_id, installation.module_id, "APPLICATION_EXTENSION_LIFECYCLE_FAILED",
            operation=ticket.operation, outcome="execution_unconfirmed",
        )


def _prepare_lifecycle(db, module_id):
    try:
        guard = read_authority_guard(db)
        installation = _installation(db, module_id)
        return guard, read_application_authority(db, installation.id), _lifecycle_state(installation)
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc


def _recheck_lifecycle(db, authority, expected, state):
    authority.lock_application(expected)
    installation = db.get(
        ApplicationExtensionInstallation, expected.installation_id, populate_existing=True
    )
    if installation is None or _lifecycle_state(installation) != state:
        authority.reject()
    return installation


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
    if installation.active_version != package.version or installation.module_id != package.module_id:
        raise HTTPException(409, "Active application package version is inconsistent")
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


@router.get("/packages/{sha256}/configuration")
def application_package_configuration(
    sha256: str,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None:
        raise HTTPException(404, "Application package was not found")
    definition = _definition(package)
    schema = package.manifest.get("configuration_schema") or {}
    properties = schema.get("properties") or {}
    installation = db.scalar(
        select(ApplicationExtensionInstallation).where(
            ApplicationExtensionInstallation.module_id == package.module_id
        )
    )
    current = dict(package.manifest.get("configuration_defaults") or {})
    if installation is not None:
        current.update(installation.configuration or {})
    fields = []
    for key in device_configuration_keys(definition):
        field_schema = properties.get(key) if isinstance(properties, dict) else None
        field_schema = field_schema if isinstance(field_schema, dict) else {}
        fields.append(
            {
                "key": key,
                "kind": "device",
                "label": field_schema.get("title") or key.replace("_", " ").title(),
                "description": field_schema.get("description"),
                "required": True,
                "value": current.get(key),
            }
        )
    devices = list(
        db.scalars(
            select(Device)
            .where(Device.revoked_at.is_(None))
            .order_by(Device.display_name, Device.device_id)
        )
    )
    return {
        "module_id": package.module_id,
        "version": package.version,
        "fields": fields,
        "devices": [
            {
                "device_id": device.device_id,
                "display_name": device.display_name,
                "role": device.role,
            }
            for device in devices
        ],
    }


@router.post("/packages/{sha256}/activate", response_model=ApplicationInstallationResponse)
def activate_application_extension(
    sha256: str,
    request: ApplicationActivationRequest | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    actor_id = admin.id
    try:
        guard = read_authority_guard(db)
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc
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
    try:
        expected = read_application_authority(db, installation.id) if installation else None
    except AuthorityMetadataError as exc:
        raise HTTPException(409, str(exc)) from exc
    state = _lifecycle_state(installation) if installation else None
    candidate = _package_state(package)
    package_id, module_id, version = package.id, package.module_id, package.version
    helper = UpdateHelperClient(
        get_settings().applications.helper_socket,
        timeout_seconds=definition.service.startup_timeout_seconds + 10,
    )
    try:
        validate_public_http_candidate(db, package, definition)
    except ApplicationPublicWebError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    requested_configuration = request.configuration if request is not None else {}
    configurable_device_keys = set(device_configuration_keys(definition))
    if set(requested_configuration) - configurable_device_keys:
        raise HTTPException(
            422,
            "Only declared device bindings can be configured during activation",
        )
    try:
        resolved_configuration = resolve_application_configuration(
            package.manifest.get("configuration_schema") or {},
            package.manifest.get("configuration_defaults") or {},
            definition,
            existing=(installation.configuration if installation is not None else None),
            overrides=requested_configuration,
        )
    except ApplicationConfigurationError as exc:
        raise HTTPException(422, str(exc)) from exc
    available_device_ids = set(
        db.scalars(select(Device.device_id).where(Device.revoked_at.is_(None)))
    )
    unavailable = sorted(
        key
        for key in configurable_device_keys
        if resolved_configuration.get(key) not in available_device_ids
    )
    if unavailable:
        raise HTTPException(
            422,
            "Select an available device for: " + ", ".join(unavailable),
        )
    with _activation_authority(db, expected, sha256, resolved_configuration, guard), _lifecycle_write(db, expected_guard=guard) as authority:
        package = db.get(ModulePackage, package_id, populate_existing=True)
        if package is None or _package_state(package) != candidate:
            authority.reject()
        if expected is None:
            if db.scalar(select(ApplicationExtensionInstallation.id).where(
                ApplicationExtensionInstallation.module_id == module_id
            )) is not None:
                authority.reject()
            installation = ApplicationExtensionInstallation(
                module_id=module_id, module_package_id=package_id,
                instance_id=application_instance_id(module_id),
                socket_path="pending", status="staged", enabled=False,
            )
            db.add(installation)
            db.flush()
        else:
            installation = _recheck_lifecycle(db, authority, expected, state)
        # Device revocation is not yet a participating authority writer.
        current_devices = set(db.scalars(
            select(Device.device_id).where(Device.revoked_at.is_(None))
        ))
        if any(resolved_configuration.get(key) not in current_devices
               for key in configurable_device_keys):
            authority.reject()
        installation.previous_package_id = (
            installation.module_package_id if installation.enabled else None
        )
        installation.module_package_id = package_id
        installation.configuration = resolved_configuration
        ticket = _start_lifecycle(db, authority, installation, "activating", actor_id)
    try:
        result = helper.activate_application_extension(
            sha256, actor_id, resolved_configuration, _helper_lifecycle(ticket)
        )
        if (
            not isinstance(result, dict)
            or result.get("module_id") != module_id or result.get("version") != version
            or result.get("sha256", sha256) != sha256
            or not isinstance(result.get("instance_id"), str)
            or len(result["instance_id"]) != 24
            or any(c not in "0123456789abcdef" for c in result["instance_id"])
            or not isinstance(result.get("socket_path"), str) or not result["socket_path"]
        ):
            raise UpdateHelperError("Application helper returned another package identity")
    except UpdateHelperError as exc:
        _lifecycle_failed(db, ticket, actor_id)
        raise HTTPException(409, "Application extension activation failed; recovery is required") from exc
    with _lifecycle_write(db) as authority:
        installation = _lock_lifecycle(db, authority, ticket)
        package = db.get(ModulePackage, package_id, populate_existing=True)
        if package is None or _package_state(package) != candidate:
            authority.reject()
        installation.instance_id = result["instance_id"]
        installation.socket_path = result["socket_path"]
        installation.active_version = version
        installation.status = "active"
        installation.enabled = True
        installation.activated_at = datetime.now(UTC)
        installation.health_checked_at = datetime.now(UTC)
        installation.error = None
        installation.configuration = resolved_configuration
        _lifecycle_audit(
            db, actor_id, module_id, "APPLICATION_EXTENSION_ACTIVATED",
            version=version, sha256=sha256,
            configuration_keys=sorted(resolved_configuration),
        )
        response = ApplicationInstallationResponse.model_validate(installation)
    return response


@router.post("/{module_id}/disable", response_model=ApplicationInstallationResponse)
def disable_application_extension(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    actor_id = admin.id
    guard, expected, state = _prepare_lifecycle(db, module_id)
    helper = UpdateHelperClient(get_settings().applications.helper_socket)
    instance_id = state[2]
    with _lifecycle_write(db, expected_guard=guard) as authority:
        installation = _recheck_lifecycle(db, authority, expected, state)
        ticket = _start_lifecycle(db, authority, installation, "disabling", actor_id)
    try:
        helper.disable_application_extension(instance_id, actor_id, _helper_lifecycle(ticket))
    except UpdateHelperError as exc:
        _lifecycle_failed(db, ticket, actor_id)
        raise HTTPException(409, "Application extension could not be disabled; recovery is required") from exc
    with _lifecycle_write(db) as authority:
        installation = _lock_lifecycle(db, authority, ticket)
        installation.status = "disabled"
        installation.error = None
        _lifecycle_audit(
            db, actor_id, module_id, "APPLICATION_EXTENSION_DISABLED",
            version=installation.active_version,
        )
        response = ApplicationInstallationResponse.model_validate(installation)
    return response


@router.delete("/{module_id}")
def uninstall_application_extension(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from backend.db.application_command import ApplicationCommandEpoch, ApplicationCommandRequest
    from backend.services.installation_peers import invalidate_application_peers
    actor_id = admin.id
    guard, expected, state = _prepare_lifecycle(db, module_id)
    instance_id, version = state[2], state[3]
    helper = UpdateHelperClient(get_settings().applications.helper_socket)
    with _lifecycle_write(db, expected_guard=guard) as authority:
        installation = _recheck_lifecycle(db, authority, expected, state)
        if db.scalar(select(ApplicationJobState.id).where(
            ApplicationJobState.application_installation_id == installation.id,
            ApplicationJobState.lease_token.is_not(None),
        )) is not None:
            raise HTTPException(409, "Disable the application and resolve outstanding job claims before uninstalling")
        invalidate_application_peers(db, module_id)
        ticket = _start_lifecycle(db, authority, installation, "uninstalling", actor_id)
    try:
        helper.uninstall_application_extension(instance_id, actor_id, _helper_lifecycle(ticket))
    except UpdateHelperError as exc:
        _lifecycle_failed(db, ticket, actor_id)
        raise HTTPException(409, "Application extension could not be uninstalled; recovery is required") from exc

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
    with _lifecycle_write(db) as authority:
        installation = _lock_lifecycle(db, authority, ticket)
        for model in owned_models:
            db.execute(
                delete(model).where(model.application_installation_id == installation.id)
            )
        db.execute(delete(role_application_grants).where(role_application_grants.c.installation_id == installation.id))
        db.execute(delete(ApplicationCommandRequest).where(ApplicationCommandRequest.installation_id == installation.id))
        db.execute(delete(ApplicationCommandEpoch).where(ApplicationCommandEpoch.installation_id == installation.id))
        db.delete(installation)
        _lifecycle_audit(
            db, actor_id, module_id, "APPLICATION_EXTENSION_UNINSTALLED",
            version=version, data_preserved=True,
        )
    return {
        "status": "uninstalled",
        "module_id": module_id,
        "version": version,
        "data_preserved": True,
    }


@router.post("/{module_id}/lifecycle/recover", response_model=ApplicationInstallationResponse)
def recover_application_extension(
    module_id: str,
    request: ApplicationLifecycleRecoveryRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Explicitly reconcile uncertain runtime work to disabled, never to active."""
    actor_id = admin.id
    guard, expected, state = _prepare_lifecycle(db, module_id)
    if state[4] not in {"activating", "disabling", "uninstalling", "recovering", "recovery_required"}:
        raise HTTPException(409, "Only an interrupted or unconfirmed lifecycle can be recovered")
    helper = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=45)
    with _lifecycle_write(db, expected_guard=guard) as authority:
        # Unlike ordinary management, recovery can supersede an exact pending
        # ticket. The helper serialization/fresh DB check fences delayed work.
        authority.lock_application(expected, lifecycle_status=state[4])
        installation = db.get(ApplicationExtensionInstallation, expected.installation_id, populate_existing=True)
        if installation is None or _lifecycle_state(installation) != state:
            authority.reject()
        ticket = _start_lifecycle(db, authority, installation, "recovering", actor_id)
    context = _helper_lifecycle(ticket)
    try:
        result = helper.recover_application_extension(state[2], actor_id, context)
        if (not isinstance(result, dict) or result.get("status") != "disabled"
                or result.get("instance_id") != state[2] or result.get("lifecycle") != context
                or result.get("quiescent") is not True):
            raise UpdateHelperError("Application runtime recovery evidence is invalid")
    except UpdateHelperError as exc:
        _lifecycle_failed(db, ticket, actor_id)
        raise HTTPException(409, "Application runtime could not be confirmed stopped; recovery is required") from exc
    with _lifecycle_write(db) as authority:
        installation = _lock_lifecycle(db, authority, ticket)
        installation.status = "disabled"
        installation.enabled = False
        # We proved quiescence, not which package/data migration succeeded.
        installation.active_version = None
        installation.health_checked_at = None
        installation.error = None
        _lifecycle_audit(
            db, actor_id, module_id, "APPLICATION_EXTENSION_LIFECYCLE_RECOVERED",
            previous_status=state[4], outcome="stopped_disabled",
            external_outcome_reviewed=request.confirmed_external_outcome_reviewed,
            data_preserved=True,
        )
        response = ApplicationInstallationResponse.model_validate(installation)
    return response


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
    if not can_access_application_operation(
        operation, ApplicationPrincipal(kind="user", user_id=user.id, is_admin=user.role == "admin"),
        audience="operator", permission_ids=permission_ids,
    ):
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


@router.get("/{module_id}/access", response_model=ApplicationAccessResponse)
def get_application_access(
    module_id: str,
    response: Response,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
):
    user = _user_from_claims(db, claims)
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    definition = _definition(package)
    principal = ApplicationPrincipal(kind="user", user_id=user.id, is_admin=user.role == "admin")
    permissions = application_permission_ids(db, installation.id, user.id)
    response.headers["Cache-Control"] = "no-store"
    return ApplicationAccessResponse(
        module_id=module_id, active_version=package.version, user_id=user.id,
        allowed_route_ids=sorted(route.route_id for route in definition.routes
            if can_access_application_route(route, principal, module_id=module_id, permission_ids=permissions)),
        allowed_operation_ids=sorted(operation.operation_id for operation in definition.operations
            if any(can_access_application_operation(operation, principal, audience=audience, permission_ids=permissions)
                   for audience in ("public", "operator", "administrator"))),
    )


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
