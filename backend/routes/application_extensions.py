"""Lifecycle, authorization and operation gateway for application extensions."""

from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.config import get_settings
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
    ApplicationRetainedData,
    ApplicationSecretReference,
    ApplicationSyncCheckpoint,
    ModulePackage,
)
from backend.db.user import User
from backend.db.application_task import ApplicationTaskRun, ApplicationTaskSchedule
from backend.db.association_tables import role_application_grants
from backend.services.application_extensions import (
    ApplicationGatewayError,
    find_operation,
    load_application_definition,
)
from backend.services.application_public_web import (
    ApplicationPublicWebError,
    validate_public_http_candidate,
)
from backend.services.application_configuration import (
    ApplicationConfigurationError,
    device_configuration_keys,
    resolve_device_selection, require_available_device_bindings,
)
from backend.services.module_packages import ModulePackageError
from backend.services.application_code_scope import code_verification_scope
from backend.services.application_requirements import (
    ApplicationRequirementsError, inspect_platform_requirements, require_platform_requirements,
)
from backend.services.application_access import (
    application_permission_ids, ApplicationPrincipal,
    can_access_application_route, can_access_application_operation,
    resolve_application_principal,
)
from backend.services.application_lifecycle import (
    _helper_lifecycle, _lifecycle_state, _package_state,
    _lifecycle_audit, _start_lifecycle, _lock_lifecycle,
)
from backend.services.application_consent_lifecycle import (
    prepare_lifecycle_consent, completing_lifecycle_consent,
)
from backend.routes.application_tasks import router as task_reconciliation_router
from backend.services.authority_metadata import (
    AuthorityMetadataError,
    authority_transaction,
    read_application_authority,
    read_authority_guard,
)
from backend.utils.auth_dep import require_admin, require_user
from backend.utils.db_utils import get_db
from three_mm_protocol.module_manifest import MODULE_ID_PATTERN
from three_mm_runtime.update_helper_client import (
    APPLICATION_ACTIVATION_SETUP_BUDGET_SECONDS, UpdateHelperClient, UpdateHelperError,
)
from three_mm_runtime.application_activation import application_instance_id
from three_mm_runtime.application_transport import ApplicationTransportError


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


class ApplicationInstallationCatalogResponse(ApplicationInstallationResponse):
    package_sha256: str | None


class ApplicationActivationRequest(BaseModel):
    configuration: dict[str, object] | None = None

    model_config = ConfigDict(extra="forbid")


class StageApplicationPackageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_artifact_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    configuration: dict | None = Field(default=None, max_length=64)


class ApplicationAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    module_id: str
    active_version: str
    user_id: int
    subject_id: str
    platform_administrator: bool
    permission_ids: list[str]
    allowed_route_ids: list[str]
    allowed_operation_ids: list[str]


class ApplicationUiBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    host_version: Literal[1]
    entrypoint_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    built_ui_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("host_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Unsupported application host version")
        return value


class ApplicationOperationRequest(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=160)
    ui_context: ApplicationUiBinding | None = None

    model_config = ConfigDict(extra="forbid")


class ApplicationPermissionGrantRequest(BaseModel):
    user_id: int = Field(gt=0)
    permission_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=96)

    model_config = ConfigDict(extra="forbid")








class ApplicationLifecycleRecoveryRequest(BaseModel):
    confirmed_external_outcome_reviewed: Literal[True]

    model_config = ConfigDict(extra="forbid")


INTERRUPTED_LIFECYCLE_STATUSES = frozenset({
    "activating", "disabling", "uninstalling", "recovering", "recovery_required",
})


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


@contextmanager
def _activation_authority(db, expected, sha256, configuration, guard):
    if expected is None or expected.mode == 'compatibility':
        yield
        return
    from backend.services.application_authority_management import configured_manager, AuthorityManagementError
    from backend.services.application_authority_keys import AuthorityReviewKeyError
    try:
        with configured_manager(db.get_bind().engine).native_activation(
                expected.installation_id, sha256, configuration, guard) as key:
            yield key
    except (AuthorityManagementError, AuthorityReviewKeyError, ValueError):
        raise HTTPException(409, 'Application access for this exact package is required. Stop the application, prepare the selected version and approve its access before activation.') from None


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


def _recheck_lifecycle(db, authority, expected, state, *, lifecycle_status=None):
    authority.lock_application(expected, lifecycle_status=lifecycle_status)
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








async def _invoke_http(db, module_id, operation_id, request, audience, authorization=None):
    from backend.services.application_invocation_relay import InvocationSpec, invoke_with_relay
    correlation_id=uuid.uuid4().hex
    def admit():
        installation=_installation(db,module_id);package=_active_package(db,installation)
        principal=(ApplicationPrincipal(kind="anonymous") if audience=="public"
            else resolve_application_principal(authorization,db))
        permission_ids=frozenset()
        if principal.kind=="user":
            declared=frozenset(item.permission_id for item in _definition(package).permissions)
            permission_ids=application_permission_ids(db,installation.id,principal.user_id) & declared
        if audience=="administrator" and (principal.kind!="user" or not principal.is_admin):
            raise HTTPException(403,"Admin access required")
        if audience=="operator":
            if principal.kind!="user":raise HTTPException(403,"A normal user session is required")
            try:operation=find_operation(_definition(package),operation_id)
            except ApplicationGatewayError as exc:raise HTTPException(404,str(exc)) from exc
            if not can_access_application_operation(operation,principal,audience=audience,permission_ids=permission_ids):
                raise HTTPException(403,"Application permission is required")
        if audience=="kiosk" and (principal.kind!="kiosk" or principal.kiosk_module_id!=module_id):
            raise HTTPException(403,"A kiosk session for this application is required")
        if request.ui_context is not None:
            _ui_route(package,request.ui_context,principal,permission_ids,audience,db=db,installation=installation)
        context={"audience":audience,"correlation_id":correlation_id,"idempotency_key":request.idempotency_key}
        context["executor"]={"kind":"application","module_id":module_id,
            "instance_id":installation.instance_id,"artifact_sha256":package.sha256}
        if principal.kind=="user":
            context.update(user_id=principal.user_id, permission_ids=sorted(permission_ids),
                platform_administrator=principal.is_admin, subject_id=principal.subject_id)
        if audience=="kiosk":context["terminal_id"]=principal.terminal_id
        return InvocationSpec(installation,package,operation_id,request.payload,context,audience)
    def success():
        if audience=="kiosk":
            current=resolve_application_principal(authorization,db)
            terminal=db.scalar(select(ApplicationKioskTerminal).where(ApplicationKioskTerminal.terminal_id==current.terminal_id))
            if terminal is None:raise HTTPException(401,"Kiosk terminal is unavailable")
            terminal.last_seen_at=datetime.now(UTC)
    try:return await invoke_with_relay(db,get_settings().applications,admit,on_success=success)
    except ApplicationGatewayError as exc:raise HTTPException(409,str(exc)) from exc


@code_verification_scope()
def _ui_route(package, binding, principal, permission_ids, audience=None, *, db=None, installation=None):
    if binding.artifact_sha256 != package.sha256:
        raise HTTPException(409, "Application UI package changed; reload the interface")
    definition = _definition(package)
    route = next((item for item in definition.routes
                  if item.entrypoint_id == binding.entrypoint_id), None)
    if (route is None or principal is None
            or (audience is not None and route.audience != audience)
            or not can_access_application_route(
                route, principal, module_id=package.module_id, permission_ids=permission_ids)):
        raise HTTPException(403, "Application UI access is unavailable")
    mode = db.scalar(select(ApplicationExtensionInstallation.authority_mode).where(
        ApplicationExtensionInstallation.id == installation.id)) if db is not None and installation is not None else None
    if binding.built_ui_sha256 is not None or (installation is not None and mode != 'compatibility'):
        from backend.services.compiled_ui import application_ui_artifact, CompiledUiBuildError
        try:
            if binding.built_ui_sha256 is None:
                raise CompiledUiBuildError('Application UI build binding is required')
            from backend.services.application_extensions import load_application_package
            validated = load_application_package(package)
            if validated.sha256 != package.sha256:
                raise CompiledUiBuildError('Application UI package changed')
            application_ui_artifact(db, installation, validated, expected_build=binding.built_ui_sha256)
        except (CompiledUiBuildError, ApplicationGatewayError, ModulePackageError, OSError):
            raise HTTPException(409, 'Application UI build is unavailable; reload the interface') from None
    return definition, route


def _retained_identity(module_id):
    if type(module_id) is not str or len(module_id) > 160 or re.fullmatch(MODULE_ID_PATTERN, module_id) is None:
        raise HTTPException(422, "Application identity is invalid")
    return application_instance_id(module_id)


def _application_data_name(package, module_id):
    manifest = package.manifest if package is not None and isinstance(package.manifest, dict) else {}
    name = manifest.get("name")
    return name[:255] if type(name) is str and name.strip() else module_id


def _retain_application_data(db, module_id, instance_id, name):
    _retained_identity(module_id)
    if type(instance_id) is not str or re.fullmatch(r"[0-9a-f]{24}", instance_id) is None:
        raise HTTPException(409, "Application data identity is invalid")
    row = db.get(ApplicationRetainedData, module_id, populate_existing=True)
    if row is None:
        row = ApplicationRetainedData(module_id=module_id, instance_id=instance_id, name=name)
        db.add(row)
    elif row.instance_id != instance_id:
        raise HTTPException(409, "Application retained data identity changed")
    else:
        row.name = name
    return row


def _require_uninstalled_data(db, module_id, instance_id):
    if db.scalar(select(ApplicationExtensionInstallation.id).where(or_(
        ApplicationExtensionInstallation.module_id == module_id,
        ApplicationExtensionInstallation.instance_id == instance_id,
    ))) is not None:
        raise HTTPException(409, "Uninstall the application extension before erasing data")


@router.get("/retained-data")
def list_retained_application_data(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApplicationRetainedData).where(~select(ApplicationExtensionInstallation.id).where(or_(
        ApplicationExtensionInstallation.module_id == ApplicationRetainedData.module_id,
        ApplicationExtensionInstallation.instance_id == ApplicationRetainedData.instance_id,
    )).exists()).order_by(ApplicationRetainedData.name, ApplicationRetainedData.module_id))
    result = []
    for row in rows:
        _retained_identity(row.module_id)
        if type(row.instance_id) is not str or re.fullmatch(r"[0-9a-f]{24}", row.instance_id) is None:
            raise HTTPException(409, "Application retained data identity is invalid")
        result.append({"module_id": row.module_id, "instance_id": row.instance_id, "name": row.name or row.module_id})
    return result


@router.get("/{module_id}/ui-host/{entrypoint_id}")
def get_application_ui_host(
    module_id: str,
    entrypoint_id: str,
    artifact_sha256: str,
    response: Response,
    built_ui_sha256: str | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Fresh, credential-free UI description, not a resource authority grant."""
    try:
        binding = ApplicationUiBinding(
            host_version=1, entrypoint_id=entrypoint_id, artifact_sha256=artifact_sha256,
            built_ui_sha256=built_ui_sha256)
    except ValueError:
        raise HTTPException(422, "Application UI binding is invalid") from None
    principal = resolve_application_principal(authorization, db)
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    permissions = (application_permission_ids(db, installation.id, principal.user_id)
                   if principal.kind == "user" else frozenset())
    definition, route = _ui_route(package, binding, principal, permissions, db=db, installation=installation)
    response.headers["Cache-Control"] = "no-store"
    return {
        **binding.model_dump(exclude_none=True),
        "module_id": module_id,
        "active_version": package.version,
        "audience": route.audience,
        "features": {"operations": True, "resource_authority": "separate",
                     "presentation_version": 1,
                     "browser_isolation": False,
                     "administration_reads": list(route.administration_reads),
                     "administration_actions": list(route.administration_actions)},
        "operations": [
            {"operation_id": operation.operation_id, "kind": operation.kind,
             "idempotency": operation.idempotency}
            for operation in definition.operations
            if (route.audience == "kiosk" and "kiosk" in operation.audiences)
            or can_access_application_operation(
                operation, principal, audience=route.audience, permission_ids=permissions)
        ],
    }


@contextmanager
def _administration_read(db, module_id, binding, authorization, read):
    """Current native code trust, actor and route in one read-only snapshot.

    The application receives neither a service grant nor a reusable credential.
    Each read is admitted independently; ui-host discovery is not authorization.
    """
    from backend.services.application_authority_sources import _read_snapshot, _Unavailable
    from backend.services.application_authority_management import configured_manager, AuthorityManagementError
    from backend.services.application_authority_keys import AuthorityReviewKeyError

    try:
        engine = db.get_bind().engine
        with _read_snapshot(engine) as current:
            principal = resolve_application_principal(authorization, current)
            if principal.kind != "user" or not principal.is_admin:
                raise HTTPException(403, "Current administrator access is required")
            installation = _installation(current, module_id)
            if installation.authority_mode == "compatibility":
                raise HTTPException(403, "Reviewed native UI is required")
            installation_id = installation.id
        with configured_manager(engine).ui_trust_snapshot(installation_id, binding.built_ui_sha256) as current:
            principal = resolve_application_principal(authorization, current)
            if principal.kind != "user" or not principal.is_admin:
                raise HTTPException(403, "Current administrator access is required")
            installation = _installation(current, module_id)
            package = _active_package(current, installation)
            _, route = _ui_route(package, binding, principal, frozenset(), "administrator",
                                 db=current, installation=installation)
            if read not in route.administration_reads:
                raise HTTPException(403, "Administrator read is not declared by this route")
            yield current
    except (AuthorityManagementError, AuthorityReviewKeyError, _Unavailable, OSError, ValueError):
        raise HTTPException(403, "Current administrator UI access is unavailable") from None


def _administration_binding(entrypoint_id, artifact_sha256, built_ui_sha256):
    try:
        return ApplicationUiBinding(host_version=1, entrypoint_id=entrypoint_id,
            artifact_sha256=artifact_sha256, built_ui_sha256=built_ui_sha256)
    except ValueError:
        raise HTTPException(422, "Application UI binding is invalid") from None


@router.get("/{module_id}/ui-host/{entrypoint_id}/devices")
def read_application_devices(
    module_id: str, entrypoint_id: str, artifact_sha256: str, built_ui_sha256: str,
    response: Response, offset: int = Query(default=0, ge=0, le=9_007_199_254_740_991),
    limit: int = Query(default=50, ge=1, le=100),
    authorization: str | None = Header(default=None), db: Session = Depends(get_db),
):
    from backend.services.device_registry_read import read_devices
    response.headers["Cache-Control"] = "no-store"
    binding = _administration_binding(entrypoint_id, artifact_sha256, built_ui_sha256)
    with _administration_read(db, module_id, binding, authorization, "devices.list") as current:
        return read_devices(current, inventory_schema_version=2, offset=offset, limit=limit)


@router.get("/{module_id}/ui-host/{entrypoint_id}/devices/{device_id}")
def read_application_device(
    module_id: str, entrypoint_id: str, device_id: str,
    artifact_sha256: str, built_ui_sha256: str, response: Response,
    authorization: str | None = Header(default=None), db: Session = Depends(get_db),
):
    from backend.services.device_registry_read import read_device
    response.headers["Cache-Control"] = "no-store"
    binding = _administration_binding(entrypoint_id, artifact_sha256, built_ui_sha256)
    if re.fullmatch(r"dev_[0-9a-f]{32}", device_id) is None:
        raise HTTPException(422, "Device identity is invalid")
    with _administration_read(db, module_id, binding, authorization, "devices.detail") as current:
        return read_device(device_id, current, inventory_schema_version=2)


@router.get("", response_model=list[ApplicationInstallationCatalogResponse])
def list_application_extensions(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(ApplicationExtensionInstallation, ModulePackage.sha256)
        .outerjoin(ModulePackage, ModulePackage.id == ApplicationExtensionInstallation.module_package_id)
        .order_by(ApplicationExtensionInstallation.module_id))
    return [{**ApplicationInstallationResponse.model_validate(installation).model_dump(),
        'package_sha256': sha256} for installation, sha256 in rows]


@router.post('/packages/{sha256}/stage', dependencies=[Depends(require_admin)])
def stage_application_package(sha256: str, request: StageApplicationPackageRequest,
        authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(401, 'A current administrator login is required')
    from backend.services.application_package_staging import stage_application_package as stage
    from backend.services.application_authority_management import AuthorityManagementError
    from backend.services.application_authority_keys import AuthorityReviewKeyError
    try:
        return stage(db.get_bind().engine, sha256, request, authorization.split(' ', 1)[1])
    except ApplicationRequirementsError as error:
        raise HTTPException(409, str(error)) from None
    except AuthorityManagementError as error:
        raise HTTPException(403 if error.reason == 'actor_unavailable' else 409,
            'Application package preparation is unavailable. Refresh its current access and state.') from None
    except (AuthorityReviewKeyError, ValueError, OSError, RuntimeError):
        raise HTTPException(409, 'Stop the application and refresh its exact package review before preparation. Relational migrations and session providers require their dedicated prepared lifecycle.') from None


@router.get('/packages/{sha256}/platform-requirements')
def application_package_requirements(sha256: str, response: Response,
        _admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None:
        raise HTTPException(404, 'Application package was not found')
    try:
        definition = _definition(package)
    except ApplicationGatewayError as error:
        raise HTTPException(409, str(error)) from None
    return {'artifact_sha256': package.sha256, 'module_id': definition.module_id,
        'version': definition.version, **inspect_platform_requirements(definition).model_dump(mode='json')}


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
        optional=set(device_configuration_keys(definition))-set(device_configuration_keys(definition,required_only=True))
        for key in optional-set(installation.configuration or {}):current.pop(key,None)
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
                "required": key in device_configuration_keys(definition, required_only=True) or key in schema.get('required', []),
                "value": current.get(key),
            }
        )
    devices = list(
        db.scalars(
            select(Device)
            .where(Device.revoked_at.is_(None),Device.approved_at.is_not(None))
            .order_by(Device.display_name, Device.device_id)
        )
    )
    device_values = [{'device_id': device.device_id, 'display_name': device.display_name, 'role': device.role} for device in devices]
    module_id, version = package.module_id, package.version
    if definition.query_dependencies:
        from backend.services.application_query_configuration import configuration_fields
        engine = db.get_bind().engine
        db.rollback()  # No routing transaction spans candidate ZIP validation.
        fields.extend(configuration_fields(engine, definition, current))
    return {
        "module_id": module_id,
        "version": version,
        "fields": fields,
        "command_bindings": [{
            "binding_id": item.binding_id,
            "target_device_config_key": item.target_device_config_key,
            "capability_id": item.capability_id,
            "contract_version": item.contract_version,
            "action": item.action,
        } for item in definition.command_bindings],
        "devices": device_values,
    }


@router.get("/packages/{sha256}/command-bindings/{binding_id}/discovery")
def discover_application_command_candidates(
    sha256: str, binding_id: str, response: Response,
    after_device_id: str | None = None,
    _admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    from backend.services.application_command_discovery import discover_candidates
    from three_mm_protocol.application_command_discovery import DeviceId
    from pydantic import TypeAdapter

    response.headers["Cache-Control"] = "no-store"
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == sha256))
    if package is None:
        raise HTTPException(404, "Application package was not found")
    definition = _definition(package)
    installation = db.scalar(select(ApplicationExtensionInstallation).where(
        ApplicationExtensionInstallation.module_id == package.module_id))
    try:
        if after_device_id is not None:
            TypeAdapter(DeviceId).validate_python(after_device_id, strict=True)
        return discover_candidates(db, definition, binding_id,
            configuration=installation.configuration if installation else None,
            after_device_id=after_device_id)
    except ValueError:
        raise HTTPException(400, "Command discovery request or declaration is invalid") from None


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
        require_platform_requirements(definition)
    except ApplicationRequirementsError as exc:
        raise HTTPException(409, str(exc)) from None
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
        timeout_seconds=definition.service.startup_timeout_seconds + APPLICATION_ACTIVATION_SETUP_BUDGET_SECONDS,
    )
    try:
        validate_public_http_candidate(db, package, definition)
    except ApplicationPublicWebError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    requested_configuration = (request.configuration or {}) if request is not None else {}
    from backend.services.application_configuration import binding_configuration_keys
    configurable_device_keys = set(binding_configuration_keys(definition))
    if set(requested_configuration) - configurable_device_keys:
        raise HTTPException(
            422,
            "Only declared resource bindings can be configured during activation",
        )
    try:
        resolved_configuration = resolve_device_selection(
            package.manifest.get("configuration_schema") or {},
            package.manifest.get("configuration_defaults") or {},
            definition,
            existing=(installation.configuration if installation is not None else None),
            selection=request.configuration if request is not None else None,
        )
    except ApplicationConfigurationError as exc:
        raise HTTPException(422, str(exc)) from exc
    available_device_ids = set(
        db.scalars(select(Device.device_id).where(Device.revoked_at.is_(None),Device.approved_at.is_not(None)))
    )
    try:
        require_available_device_bindings(definition,resolved_configuration,available_device_ids)
    except ApplicationConfigurationError as exc:
        raise HTTPException(422,str(exc)) from None
    consent = prepare_lifecycle_consent(db.get_bind().engine, expected)
    with _activation_authority(db, expected, sha256, resolved_configuration, guard) as key, _lifecycle_write(db, expected_guard=guard) as authority:
        saved_consent = consent.capture(db, key)
        package = db.get(ModulePackage, package_id, populate_existing=True)
        if package is None or _package_state(package) != candidate:
            authority.reject()
        if expected is None:
            if db.scalar(select(ApplicationExtensionInstallation.id).where(
                ApplicationExtensionInstallation.module_id == module_id
            )) is not None:
                authority.reject()
            desired_instance_id = application_instance_id(module_id)
            retained = db.get(ApplicationRetainedData, module_id, populate_existing=True)
            if retained is not None and retained.instance_id != desired_instance_id:
                raise HTTPException(
                    409,
                    "Erase preserved application data before activating a new runtime identity",
                )
            installation = ApplicationExtensionInstallation(
                module_id=module_id, module_package_id=package_id,
                instance_id=desired_instance_id,
                socket_path="pending", status="staged", enabled=False,
                authority_mode="review_required",
            )
            db.add(installation)
            db.flush()
        else:
            installation = _recheck_lifecycle(db, authority, expected, state)
        # Device revocation is not yet a participating authority writer.
        current_devices = set(db.scalars(
            select(Device.device_id).where(Device.revoked_at.is_(None),Device.approved_at.is_not(None))
        ))
        try: require_available_device_bindings(definition,resolved_configuration,current_devices)
        except ApplicationConfigurationError: authority.reject()
        if installation.enabled or installation.module_package_id != package_id:
            installation.previous_package_id = installation.module_package_id
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
    with completing_lifecycle_consent(saved_consent) as consent, _lifecycle_write(db) as authority:
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
        consent.resume(db, installation, actor_id)
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
    consent = prepare_lifecycle_consent(db.get_bind().engine, expected)
    with consent.lease() as key, _lifecycle_write(db, expected_guard=guard) as authority:
        installation = _recheck_lifecycle(db, authority, expected, state)
        saved_consent = consent.capture(db, key)
        ticket = _start_lifecycle(db, authority, installation, "disabling", actor_id)
    try:
        helper.disable_application_extension(instance_id, actor_id, _helper_lifecycle(ticket))
    except UpdateHelperError as exc:
        _lifecycle_failed(db, ticket, actor_id)
        raise HTTPException(409, "Application extension could not be disabled; recovery is required") from exc
    with completing_lifecycle_consent(saved_consent) as consent, _lifecycle_write(db) as authority:
        installation = _lock_lifecycle(db, authority, ticket)
        installation.status = "disabled"
        installation.error = None
        consent.resume(db, installation, actor_id)
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
    recovered_for_removal = state[4] in INTERRUPTED_LIFECYCLE_STATUSES
    if recovered_for_removal:
        _, recovered_owner, recovered_state = _recover_lifecycle(module_id, actor_id, db, removing=True)
        guard, expected, state = _prepare_lifecycle(db, module_id)
        if expected != recovered_owner or state != recovered_state:
            raise HTTPException(409, "Application changed after stopping; refresh before removing it")
    instance_id, version = state[2], state[3]
    helper = UpdateHelperClient(get_settings().applications.helper_socket)
    with _lifecycle_write(db, expected_guard=guard) as authority:
        installation = _recheck_lifecycle(
            db, authority, expected, state,
            lifecycle_status="recovering" if recovered_for_removal else None,
        )
        _require_no_unresolved_tasks(db, installation.id)
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
        db.execute(delete(ApplicationTaskRun).where(ApplicationTaskRun.installation_id == installation.id))
        db.execute(delete(ApplicationTaskSchedule).where(ApplicationTaskSchedule.installation_id == installation.id))
        package = db.get(ModulePackage, installation.module_package_id)
        _retain_application_data(db, module_id, instance_id, _application_data_name(package, module_id))
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


def _require_no_unresolved_tasks(db, installation_id):
    from backend.services.application_tasks import require_quiescent_task_journal
    try:
        require_quiescent_task_journal(db,installation_id)
    except ValueError as error:
        raise HTTPException(409,str(error)) from None
    # Retained pre-task outcomes are historical recovery evidence only. Their
    # old executor remains unavailable; never erase an unresolved historical claim.
    if db.scalar(select(ApplicationJobState.id).where(
        ApplicationJobState.application_installation_id == installation_id,
        ApplicationJobState.lease_token.is_not(None),
    )) is not None:
        raise HTTPException(409, "Disable the application and resolve outstanding job claims before uninstalling")


def _recover_lifecycle(module_id, actor_id, db, *, removing=False, external_outcome_reviewed=False):
    """Quiesce an exact pending generation; no activation, rollback or replay.

    Removal retires the application and preserves its data. It never represents
    the separate operator confirmation required before recovery for future use.
    The verified runtime stays lifecycle-fenced until removal is committed.
    """
    guard, expected, state = _prepare_lifecycle(db, module_id)
    if state[4] not in INTERRUPTED_LIFECYCLE_STATUSES:
        raise HTTPException(409, "Only an interrupted or unconfirmed lifecycle can be recovered")
    helper = UpdateHelperClient(get_settings().applications.helper_socket, timeout_seconds=45)
    with _lifecycle_write(db, expected_guard=guard) as authority:
        # Unlike ordinary management, recovery can supersede an exact pending
        # ticket. The helper serialization/fresh DB check fences delayed work.
        authority.lock_application(expected, lifecycle_status=state[4])
        installation = db.get(ApplicationExtensionInstallation, expected.installation_id, populate_existing=True)
        if installation is None or _lifecycle_state(installation) != state:
            authority.reject()
        if removing:
            _require_no_unresolved_tasks(db, installation.id)
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
        installation.status = "recovering" if removing else "disabled"
        installation.enabled = False
        # We proved quiescence, not which package/data migration succeeded.
        installation.active_version = None
        installation.health_checked_at = None
        installation.error = None
        _lifecycle_audit(
            db, actor_id, module_id, "APPLICATION_EXTENSION_LIFECYCLE_RECOVERED",
            previous_status=state[4], outcome="stopped_for_removal" if removing else "stopped_disabled",
            external_outcome_reviewed=external_outcome_reviewed,
            requested_action="uninstall" if removing else "recover",
            data_preserved=True,
        )
        response = ApplicationInstallationResponse.model_validate(installation)
        removal_pin = (read_application_authority(db, installation.id), _lifecycle_state(installation))
    return (response, *removal_pin) if removing else response


@router.post("/{module_id}/lifecycle/recover", response_model=ApplicationInstallationResponse)
def recover_application_extension(
    module_id: str,
    request: ApplicationLifecycleRecoveryRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Explicitly reconcile uncertain runtime work to disabled, never to active."""
    return _recover_lifecycle(
        module_id, admin.id, db,
        external_outcome_reviewed=request.confirmed_external_outcome_reviewed,
    )


@router.delete("/{module_id}/data")
def erase_application_extension_data(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    default_instance_id = _retained_identity(module_id)
    # Persist the cleanup identity before I/O, so even an uncertain/partial erase
    # remains discoverable after the last uploaded package has been retired.
    with _lifecycle_write(db) as authority:
        row = db.get(ApplicationRetainedData, module_id, populate_existing=True)
        instance_id = row.instance_id if row is not None else default_instance_id
        if type(instance_id) is not str or re.fullmatch(r"[0-9a-f]{24}", instance_id) is None:
            raise HTTPException(409, "Application retained data identity is invalid")
        _require_uninstalled_data(db, module_id, instance_id)
        if row is None:
            packages = db.scalars(select(ModulePackage).where(ModulePackage.module_id == module_id)).all()
            package = next((item for item in packages if isinstance(item.manifest, dict)
                and isinstance(item.manifest.get("entrypoints"), dict)
                and item.manifest["entrypoints"].get("core") == "application-extension.json"), None)
            if package is None:
                raise HTTPException(404, "Application retained data was not found")
            row = _retain_application_data(db, module_id, instance_id, _application_data_name(package, module_id))
        authority.advance_guard_revision()
    failed = False
    # Unlike ordinary lifecycle I/O, erasure holds the global write guard. This
    # excludes activation until the helper's fresh no-installation proof and
    # physical removal finish. The helper reads only committed metadata.
    with _lifecycle_write(db) as authority:
        _require_uninstalled_data(db, module_id, instance_id)
        row = db.get(ApplicationRetainedData, module_id, populate_existing=True)
        if row is None or row.instance_id != instance_id:
            raise HTTPException(409, "Application retained data identity changed")
        committed_guard_revision = authority.guard.revision
        authority.advance_guard_revision()
        try:
            UpdateHelperClient(get_settings().applications.helper_socket).erase_application_extension_data(
                instance_id, admin.id, module_id=module_id, guard_generation=authority.guard.generation,
                guard_revision=committed_guard_revision,
            )
        except UpdateHelperError:
            failed = True
            _lifecycle_audit(db, admin.id, module_id, "APPLICATION_EXTENSION_DATA_ERASE_FAILED",
                             outcome="erasure_unconfirmed")
        else:
            db.delete(row)
            _lifecycle_audit(db, admin.id, module_id, "APPLICATION_EXTENSION_DATA_ERASED", data_preserved=False)
    if failed:
        raise HTTPException(409, "Application data erasure is unconfirmed; its cleanup entry is retained")
    return {"status": "erased", "module_id": module_id}


@router.post("/{module_id}/operations/{operation_id}")
async def invoke_admin_operation(module_id: str, operation_id: str, request: ApplicationOperationRequest,
    admin: User = Depends(require_admin), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return await _invoke_http(db,module_id,operation_id,request,"administrator",authorization)


@router.post("/{module_id}/public/operations/{operation_id}")
async def invoke_public_operation(module_id: str, operation_id: str, request: ApplicationOperationRequest,
    db: Session = Depends(get_db)):
    return await _invoke_http(db,module_id,operation_id,request,"public")


@router.post("/{module_id}/operator/operations/{operation_id}")
async def invoke_operator_operation(module_id: str, operation_id: str, request: ApplicationOperationRequest,
    claims: dict = Depends(require_user), authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return await _invoke_http(db,module_id,operation_id,request,"operator",authorization)


@router.post("/{module_id}/kiosk/operations/{operation_id}")
async def invoke_kiosk_operation(module_id: str, operation_id: str, request: ApplicationOperationRequest,
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return await _invoke_http(db,module_id,operation_id,request,"kiosk",authorization)


@router.get("/{module_id}/access", response_model=ApplicationAccessResponse)
def get_application_access(
    module_id: str,
    response: Response,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    user = _user_from_claims(db, claims)
    installation = _installation(db, module_id)
    package = _active_package(db, installation)
    definition = _definition(package)
    principal = resolve_application_principal(authorization, db)
    permissions = application_permission_ids(db, installation.id, user.id) & frozenset(
        item.permission_id for item in definition.permissions)
    response.headers["Cache-Control"] = "no-store"
    return ApplicationAccessResponse(
        module_id=module_id, active_version=package.version, user_id=user.id,
        subject_id=principal.subject_id,
        platform_administrator=principal.is_admin, permission_ids=sorted(permissions),
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












@router.post("/{module_id}/health")
async def check_application_health(
    module_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    waiter = None
    try:
        probe, waiter = await run_in_threadpool(_begin_application_health, db, module_id)
        response = await waiter.receive()
        return await run_in_threadpool(_finish_application_health, db, probe, response)
    except ApplicationGatewayError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OSError, ValueError, TypeError, KeyError, ImportError, RecursionError, ApplicationTransportError) as exc:
        raise HTTPException(409, "Application health response is unconfirmed") from exc
    finally:
        if waiter is not None: waiter.close()


def _begin_application_health(db, module_id):
    from backend.services.application_health_probe import begin_health_probe
    try:
        installation = _installation(db, module_id)
        return begin_health_probe(db, installation, _active_package(db, installation), get_settings().applications)
    finally:
        db.rollback()


def _finish_application_health(db, probe, response):
    from backend.services.application_health_probe import finish_health_probe
    try:
        return finish_health_probe(db, probe, response, get_settings().applications)
    finally:
        db.rollback()


# Generic administrator UI operations share the same mounted application boundary.
from backend.routes.application_administration import router as administration_router
from backend.routes.application_file_transfers import router as file_transfer_router
router.include_router(administration_router)
from backend.routes.application_connector_settings import router as connector_settings_router
router.include_router(connector_settings_router)
router.include_router(task_reconciliation_router)
router.include_router(file_transfer_router)
from backend.routes.application_delegations import router as delegation_router
router.include_router(delegation_router)

from backend.routes.application_kiosks import router as kiosk_router
router.include_router(kiosk_router)
