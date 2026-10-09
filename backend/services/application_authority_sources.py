"""Internal, read-only persisted-source resolution, NOT an approval context.

Only an existing stable installation is supported, not a staged candidate. The
separate installed authority coordinator consumes these sources and authenticates
policy/key/evidence. This read-only module alone cannot produce a reviewable
fingerprint, issuer decision or executable authority.
"""

from contextlib import contextmanager
from datetime import UTC
import hashlib
from pathlib import Path
import re
from typing import Literal
import zipfile
import zlib

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import SingletonThreadPool, StaticPool

from backend.db.device import Device, DeviceCapabilityProvider, DeviceCredential, DevicePlatformState
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.module import (
    ApplicationConnectorBinding, ApplicationExtensionInstallation,
    ApplicationSecretReference, ModuleInstallation, ModulePackage,
)
from backend.services.application_authority_context import (
    AuthorityArtifact, AuthorityBaseline, AuthorityPrincipal, Digest, ResolvedConnectorScope,
    ResolvedCredential, ResolvedEventScope, ResolvedPublicationScope, StoredConnectorScope, _bounded_json, _canonical_bytes,
)
from backend.services.application_authority_inspection import (
    AuthorityInspectionBaseline, _read_baseline,
)
from backend.services.application_configuration import resolve_application_configuration
from backend.services.application_connectors import validate_destination_origin
from backend.services.authority_metadata import (
    AuthorityGuardSnapshot, read_application_authority, read_authority_guard,
    read_connector_authority, read_device_control,
)
from backend.services.device_capability_registry import registered_capabilities
from backend.services.device_runtime_features import read_runtime_features
from three_mm_protocol.capability_contracts import CONTRACT_FEATURE, registration_contract
from three_mm_protocol.device_capabilities import ProviderId, ProviderType
from three_mm_protocol.installation_identity import InstallationIdentityV1
from three_mm_protocol.node_features import DeviceRuntimeFeaturesV1


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceIssue(SourceModel):
    scope: str | None = None
    reason: Literal[
        "source_unavailable", "snapshot_backend_unsupported", "installation_unavailable",
        "artifact_unavailable", "artifact_changed", "identity_unavailable",
        "configuration_unresolved", "device_unavailable", "device_credentials_unavailable",
        "runtime_support_unresolved", "capability_unresolved", "command_contract_unresolved",
        "connector_binding_unavailable", "connector_origin_mismatch",
        "connector_credential_unavailable", "connector_path_unsupported",
        "configuration_key_unavailable", "policy_evidence_unavailable",
        "candidate_staging_not_implemented", "command_schema_containment_not_evaluated",
        "sensor_contract_unresolved", "unsupported_scope_family",
        "peer_authority_unresolved", "frontend_authority_unresolved",
        "dependency_resolution_missing",
        "event_handler_unresolved",
    ]


class DeviceSource(SourceModel):
    device_id: str
    control_generation: str
    active_credential_ids: tuple[str, ...]
    runtime_revision: int
    runtime_name: str
    runtime_version: str
    features: tuple[str, ...]
    command_types: tuple[str, ...]


class CommandSource(SourceModel):
    scope: str
    target: DeviceSource
    sensor: DeviceSource | None
    capability_id: str
    provider_type: ProviderType
    provider_id: ProviderId
    provider_version: str = Field(min_length=1, max_length=64)
    provider_revision: int | None
    module_artifact_sha256: Digest | None
    contract_version: str
    contract_digest: str
    # Validated selected action contract, not an inferred schema/containment proof.
    action_arguments_schema: dict


class InstalledAuthoritySources(SourceModel):
    source_version: Literal[1] = 1
    source_scope: Literal["installed_command_connector_sources"] = "installed_command_connector_sources"
    sources_resolved: bool = False
    reviewable: Literal[False] = False
    context_fingerprint: None = None
    permission_approval: Literal["not_evaluated"] = "not_evaluated"
    guard: AuthorityGuardSnapshot | None = None
    principal: AuthorityPrincipal | None = None
    baseline: AuthorityBaseline | None = None
    commands: tuple[CommandSource, ...] = ()
    connectors: tuple[ResolvedConnectorScope, ...] = ()
    events: tuple[ResolvedEventScope, ...] = ()
    publications: tuple[ResolvedPublicationScope, ...] = ()
    issues: tuple[SourceIssue, ...]
    not_checked: tuple[str, ...] = (
        "candidate_staging_and_configuration_identity", "policy_trust_and_isolation_evidence",
        "approved_grants_and_current_actor", "live_health_ota_and_effect_admission",
        "restart_safe_review_clock",
    )


class _Unavailable(ValueError):
    def __init__(self, reason, scope=None):
        self.issue = SourceIssue(reason=reason, scope=scope)
        super().__init__("Authority source resolution is unavailable")


@contextmanager
def _read_snapshot(engine):
    """Dedicated connection, real snapshot and DB-enforced read-only access.

SQLite's legacy driver otherwise may not BEGIN for SELECT. Shared/in-memory
connection pools are refused: a caller's transaction must never be reused.
PostgreSQL uses its dialect's repeatable-read/read-only transaction settings;
its live concurrency acceptance is still separate from local SQLite proof.
"""
    if (
        not isinstance(engine, Engine)
        or engine.dialect.name not in {"sqlite", "postgresql"}
        or isinstance(engine.pool, (StaticPool, SingletonThreadPool))
        or (engine.dialect.name == "sqlite" and engine.url.database in {None, "", ":memory:"})
    ):
        raise _Unavailable("snapshot_backend_unsupported")
    if engine.dialect.name == "sqlite" and (
        engine.url.query.get("uri") or not Path(engine.url.database).is_file()
    ):
        # This bounded adapter accepts Core's ordinary existing file URL only,
        # not shared-cache/custom URI databases or implicit database creation.
        raise _Unavailable("snapshot_backend_unsupported")
    with engine.connect() as connection:
        previous = None
        try:
            if engine.dialect.name == "sqlite":
                if connection.exec_driver_sql("PRAGMA read_uncommitted").scalar_one() != 0:
                    raise _Unavailable("snapshot_backend_unsupported")
                previous = connection.exec_driver_sql("PRAGMA query_only").scalar_one()
                connection.exec_driver_sql("PRAGMA query_only=ON")
                connection.commit()  # PRAGMAs only; no application write.
                connection.exec_driver_sql("BEGIN")
            else:
                connection = connection.execution_options(
                    isolation_level="REPEATABLE READ", postgresql_readonly=True,
                )
                connection.begin()
            with Session(bind=connection, autoflush=False, expire_on_commit=False) as db:
                yield db
        finally:
            # Do not return a query-only connection to the ordinary writer pool.
            try:
                connection.rollback()
                if previous is not None:
                    connection.exec_driver_sql(f"PRAGMA query_only={int(previous)}")
                    connection.commit()
            except SQLAlchemyError:
                connection.invalidate()
                raise


def _package_pin(db, installation_id):
    row = db.execute(select(
        ApplicationExtensionInstallation.module_package_id,
        ApplicationExtensionInstallation.module_id,
        ApplicationExtensionInstallation.active_version,
        ApplicationExtensionInstallation.status,
        ApplicationExtensionInstallation.enabled,
        ModulePackage.module_id.label("package_module_id"),
        ModulePackage.version, ModulePackage.sha256,
    ).join(ModulePackage, ModulePackage.id == ApplicationExtensionInstallation.module_package_id)
      .where(ApplicationExtensionInstallation.id == installation_id)).one_or_none()
    if (
        row is None or row.module_id != row.package_module_id
        or row.active_version != row.version
        or (row.status, row.enabled) not in {("active", True), ("disabled", False)}
    ):
        raise _Unavailable("installation_unavailable")
    return row


def _core_identity(db):
    # Explicit public columns; never select/decrypt the private signing key.
    row = db.execute(select(
        CoreInstallationIdentity.installation_id, CoreInstallationIdentity.identity_version,
        CoreInstallationIdentity.key_generation, CoreInstallationIdentity.key_id,
        CoreInstallationIdentity.public_key, CoreInstallationIdentity.created_at,
    ).where(CoreInstallationIdentity.singleton_id == 1)).one_or_none()
    if row is None:
        raise _Unavailable("identity_unavailable")
    try:
        values = dict(row._mapping)
        if values["created_at"].tzinfo is None:
            values["created_at"] = values["created_at"].replace(tzinfo=UTC)
        return InstallationIdentityV1.model_validate(values).installation_id
    except (ValueError, TypeError, AttributeError):
        raise _Unavailable("identity_unavailable") from None


def _device(db, device_id, scope, *, command_target):
    if not isinstance(device_id, str) or re.fullmatch(r"dev_[0-9a-f]{32}", device_id) is None:
        raise _Unavailable("configuration_unresolved", scope)
    device = db.scalar(select(Device).where(Device.device_id == device_id))
    if device is None or device.approved_at is None or device.revoked_at is not None:
        raise _Unavailable("device_unavailable", scope)
    control = read_device_control(db, device.id)  # No lazy platform initialization.
    platform = db.execute(select(DevicePlatformState.authority_status, DevicePlatformState.lifecycle)
        .where(DevicePlatformState.device_id == device.id)).one()
    if platform.authority_status != "bound" or platform.lifecycle != "active":
        raise _Unavailable("device_unavailable", scope)
    credentials = tuple(db.scalars(select(DeviceCredential.credential_id)
        .where(DeviceCredential.device_id == device.id, DeviceCredential.revoked_at.is_(None))
        .order_by(DeviceCredential.credential_id).limit(65)))
    if not credentials or len(credentials) > 64 or any(
        not isinstance(item, str) or re.fullmatch(r"cred_[0-9a-f]{32}", item) is None
        for item in credentials
    ):
        raise _Unavailable("device_credentials_unavailable", scope)
    row = read_runtime_features(db, device)
    if row is None or type(row.revision) is not int or not 1 <= row.revision <= 2147483646:
        raise _Unavailable("runtime_support_unresolved", scope)
    declaration = DeviceRuntimeFeaturesV1.model_validate(_bounded_json(row.declaration))
    if declaration.device_id != device_id or (command_target and (
        CONTRACT_FEATURE not in declaration.features
        or "application.capability.invoke" not in declaration.command_types
    )):
        raise _Unavailable("runtime_support_unresolved", scope)
    return device, DeviceSource(
        device_id=device_id, control_generation=control.generation,
        active_credential_ids=credentials, runtime_revision=row.revision,
        runtime_name=declaration.runtime_name, runtime_version=declaration.runtime_version,
        features=tuple(sorted(declaration.features)), command_types=tuple(sorted(declaration.command_types)),
    )


def _registration(db, device, capability_id, scope):
    # Reuse the ONE effective registry, including its module adapter and conflict
    # rejection. Do not turn inventory offers into selected capabilities.
    registrations = _bounded_json(registered_capabilities(db, device))
    registration = next((item for item in registrations if item["capability_id"] == capability_id), None)
    if registration is None:
        raise _Unavailable("capability_unresolved", scope)
    # Pin the selected registry source, not another capability discovery path.
    # A module has an immutable package digest; non-module providers have an
    # existing declaration/configuration revision. Both share control_generation.
    provider_revision, module_digest = None, None
    if registration["provider_type"] == "agent_module":
        row = db.execute(select(ModulePackage.sha256, ModulePackage.version,
            ModuleInstallation.installed_version).join(ModuleInstallation,
                ModuleInstallation.module_package_id == ModulePackage.id)
            .where(ModuleInstallation.device_id == device.id,
                ModuleInstallation.module_id == registration["provider_id"],
                ModulePackage.module_id == registration["provider_id"],
                ModuleInstallation.enabled.is_(True), ModuleInstallation.status == "succeeded")).one_or_none()
        if row is None or row.version != registration["provider_version"] or row.installed_version != row.version:
            raise _Unavailable("capability_unresolved", scope)
        module_digest = row.sha256
    else:
        provider_revision = db.scalar(select(DeviceCapabilityProvider.revision).where(
            DeviceCapabilityProvider.device_id == device.id,
            DeviceCapabilityProvider.provider_type == registration["provider_type"],
            DeviceCapabilityProvider.provider_id == registration["provider_id"],
            DeviceCapabilityProvider.provider_version == registration["provider_version"],
            DeviceCapabilityProvider.enabled.is_(True)))
        if type(provider_revision) is not int or not 1 <= provider_revision <= 2147483646:
            raise _Unavailable("capability_unresolved", scope)
    return registration, provider_revision, module_digest


def _command(db, binding, configuration):
    scope = f"command:{binding.binding_id}"
    device, target = _device(db, configuration.get(binding.target_device_config_key), scope, command_target=True)
    registration, provider_revision, module_digest = _registration(db, device, binding.capability_id, scope)
    contract = registration_contract(binding.capability_id, registration.get("contract"))
    if (contract is None or binding.contract_version != contract.contract_version
            or binding.action not in contract.actions):
        raise _Unavailable("command_contract_unresolved", scope)
    sensor = None
    if binding.sensor_device_config_key is not None:
        _, sensor = _device(db, configuration.get(binding.sensor_device_config_key), scope, command_target=False)
    return CommandSource(scope=scope, target=target, sensor=sensor,
        capability_id=binding.capability_id, provider_type=registration["provider_type"],
        provider_id=registration["provider_id"], provider_version=registration["provider_version"],
        provider_revision=provider_revision, module_artifact_sha256=module_digest,
        contract_version=contract.contract_version, contract_digest=contract.digest(),
        action_arguments_schema=contract.actions[binding.action].arguments_schema)


def _event(db, subscription, definition, configuration):
    scope = f"event:{subscription.subscription_id}"
    device, source = _device(db, configuration.get(subscription.device_scope_config_key), scope, command_target=False)
    registration, revision, digest = _registration(db, device, subscription.capability_id, scope)
    handler = next((operation for operation in definition.operations
        if operation.operation_id == subscription.handler_operation_id), None)
    if handler is None or handler.emitted_events:
        raise _Unavailable("event_handler_unresolved", scope)
    # Pin the one selected capability/provider, current runtime/credentials and
    # actual control generation. No inventory offer or package name is a grant.
    identity = "source_" + hashlib.sha256(b"3mm:m20:resolved-event-source:v1\x00" + _canonical_bytes({
        "device": source.model_dump(mode="json"), "registration": registration,
        "provider_revision": revision, "module_artifact_sha256": digest,
    })).hexdigest()
    return ResolvedEventScope(declaration=subscription, source_device_id=source.device_id,
        source_revision=identity, handler=handler)


def _connector(db, connector, configuration, principal, installation_id):
    scope = f"connector:{connector.connector_id}"
    path = connector.path_prefix
    if (any(char in path for char in "\\%?#*") or any(char.isspace() for char in path)
            or "//" in path or any(part in {".", ".."} for part in path.split("/"))):
        raise _Unavailable("connector_path_unsupported", scope)
    row = db.execute(select(
        ApplicationConnectorBinding.id, ApplicationConnectorBinding.destination_origin,
        ApplicationConnectorBinding.secret_reference_id, ApplicationConnectorBinding.enabled,
    ).where(ApplicationConnectorBinding.application_installation_id == installation_id,
        ApplicationConnectorBinding.connector_id == connector.connector_id)).one_or_none()
    if row is None or not row.enabled:
        raise _Unavailable("connector_binding_unavailable", scope)
    metadata = read_connector_authority(db, installation_id=installation_id, binding_id=row.id)
    try:
        origin = validate_destination_origin(configuration[connector.destination_config_key], connector.allowed_schemes)
        stored_origin = validate_destination_origin(row.destination_origin, connector.allowed_schemes)
    except (ValueError, TypeError, AttributeError, RuntimeError):
        raise _Unavailable("connector_origin_mismatch", scope) from None
    if origin != stored_origin or row.destination_origin != stored_origin:
        raise _Unavailable("connector_origin_mismatch", scope)
    reference = configuration.get(connector.credential_ref_config_key) if connector.credential_ref_config_key else None
    credential = None
    if connector.authentication == "none":
        if reference is not None or row.secret_reference_id is not None:
            raise _Unavailable("connector_credential_unavailable", scope)
    else:
        secret = db.execute(select(
            ApplicationSecretReference.application_installation_id,
            ApplicationSecretReference.secret_ref, ApplicationSecretReference.credential_kind,
            ApplicationSecretReference.version, ApplicationSecretReference.revoked_at,
        ).where(ApplicationSecretReference.id == row.secret_reference_id)).one_or_none()
        if (secret is None or secret.application_installation_id != installation_id
                or secret.revoked_at is not None or secret.credential_kind != connector.authentication
                or secret.secret_ref != reference or type(secret.version) is not int):
            raise _Unavailable("connector_credential_unavailable", scope)
        credential = ResolvedCredential(owner=principal, secret_ref=secret.secret_ref,
            version=secret.version, credential_kind=secret.credential_kind, revoked=False)
    return ResolvedConnectorScope(declaration=connector, configured_origin=origin,
        configured_secret_ref=reference, stored=StoredConnectorScope(owner=principal,
            binding_revision=metadata.revision, destination_origin=stored_origin,
            enabled=True, credential=credential))


def _configuration(db, installation_id, package):
    configuration = db.scalar(select(ApplicationExtensionInstallation.configuration)
        .where(ApplicationExtensionInstallation.id == installation_id))
    try:
        if not isinstance(configuration, dict):
            raise ValueError()
        configuration = resolve_application_configuration(package.manifest.configuration_schema,
            {}, package.application_extension, existing=_bounded_json(configuration))
    except (ValueError, TypeError, RecursionError):
        raise _Unavailable("configuration_unresolved") from None
    return configuration


def _resolve(db, installation_id, pin, package):
    guard = read_authority_guard(db)  # Establish the final snapshot before resources.
    current = _package_pin(db, installation_id)
    if current != pin:
        raise _Unavailable("artifact_changed")
    authority = read_application_authority(db, installation_id)
    principal = AuthorityPrincipal(core_installation_id=_core_identity(db),
        application_installation_id=str(installation_id), incarnation=authority.incarnation,
        module_id=authority.module_id)
    configuration = _configuration(db, installation_id, package)
    app = package.application_extension
    commands = tuple(_command(db, binding, configuration) for binding in app.command_bindings)
    connectors = tuple(_connector(db, connector, configuration, principal, installation_id)
        for connector in app.connectors)
    events = tuple(_event(db, subscription, app, configuration) for subscription in app.event_subscriptions)
    publications = tuple(ResolvedPublicationScope(declaration=item,
        operation=next(operation for operation in app.operations if operation.operation_id == item.operation_id),
        service_artifact_sha256=app.service.artifact_sha256)
        for item in package.application_publications.publications) if package.application_publications else ()
    pending = [SourceIssue(reason=reason) for reason in (
        "configuration_key_unavailable", "policy_evidence_unavailable", "candidate_staging_not_implemented",
    )]
    if commands:
        pending.append(SourceIssue(reason="command_schema_containment_not_evaluated"))
    if any(binding.sensor_id is not None for binding in app.command_bindings):
        pending.append(SourceIssue(reason="sensor_contract_unresolved"))
    emitted = {event for operation in app.operations for event in operation.emitted_events}
    publication_complete = bool(publications) and emitted == {item.declaration.event_type for item in publications}
    if (app.public_http_routes or app.jobs or app.platform_permissions
            or set(package.manifest.capabilities.provides) - (emitted if publication_complete else set())
            or (emitted or "events.publish" in package.manifest.permissions) and not publication_complete):
        pending.append(SourceIssue(reason="unsupported_scope_family"))
    if app.peer_receiver is not None or any(permission.startswith("installation.peers.") for permission in app.platform_permissions):
        pending.append(SourceIssue(reason="peer_authority_unresolved"))
    if package.compiled_ui is not None:
        pending.append(SourceIssue(reason="frontend_authority_unresolved"))
    if package.manifest.dependencies or package.manifest.conflicts:
        pending.append(SourceIssue(reason="dependency_resolution_missing"))
    grant_revision = None
    if authority.mode == "enforced":
        from backend.db.application_authority_grant import ApplicationAuthorityGrant
        grant_revision = db.scalar(select(ApplicationAuthorityGrant.revision).where(
            ApplicationAuthorityGrant.installation_id == installation_id))
        if type(grant_revision) is not int or not 1 <= grant_revision < 2**53 - 1:
            raise _Unavailable("source_unavailable")
    result = InstalledAuthoritySources(sources_resolved=True, guard=guard, principal=principal,
        baseline=AuthorityBaseline(artifact=AuthorityArtifact(version=pin.version, sha256=pin.sha256),
            authority_epoch=authority.epoch, grant_revision=grant_revision, enforcement_mode=authority.mode),
        commands=commands, connectors=connectors, events=events, publications=publications, issues=tuple(pending))
    _bounded_json(result.model_dump(mode="json"))  # Total redacted output budget too.
    return result


def _prepare_installed_package(engine, installation_id, uploads_root, core_version):
    """Pin/validate bytes outside the final authoritative read transaction."""
    if type(installation_id) is not int or installation_id < 1:
        raise _Unavailable("installation_unavailable")
    with _read_snapshot(engine) as db:
        pin = _package_pin(db, installation_id)
    try:
        package = _read_baseline(AuthorityInspectionBaseline(
            pin.module_id, pin.version, pin.sha256, pin.active_version, pin.status, None,
        ), uploads_root, core_version)
    except (OSError, ValueError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, RecursionError):
        raise _Unavailable("artifact_unavailable") from None
    return pin, package


def resolve_installed_authority_sources(
    engine: Engine, installation_id: int, *, uploads_root: Path, core_version: str,
) -> InstalledAuthoritySources:
    """Inspect existing Core-owned state only; no caller snapshots/configuration.

    Artifact I/O/validation finishes OUTSIDE either read transaction. The final
    snapshot rechecks its exact installation/package pin. Result is stale evidence
    immediately after close: future apply/admission must resolve again under guard.
    Failure returns no partial resources and never raw DB/archive/config errors.
    """
    try:
        pin, package = _prepare_installed_package(engine, installation_id, uploads_root, core_version)
        with _read_snapshot(engine) as db:
            return _resolve(db, installation_id, pin, package)
    except _Unavailable as exc:
        return InstalledAuthoritySources(issues=(exc.issue,))
    except (SQLAlchemyError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return InstalledAuthoritySources(issues=(SourceIssue(reason="source_unavailable"),))
