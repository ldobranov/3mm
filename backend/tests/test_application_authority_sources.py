"""Persisted sources, secret-safe reads and actual multi-connection snapshots."""

import base64
from contextlib import contextmanager
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import threading
from types import SimpleNamespace
import zipfile

import backend.database  # noqa: F401 -- full ORM metadata
import pytest
import requests
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.base import Base
from backend.db.device import (
    Device, DeviceCapabilityProvider, DeviceCredential, DevicePlatformState,
    DeviceRuntimeFeatures,
)
from backend.db.installation_identity import CoreInstallationIdentity
from backend.db.module import (
    ApplicationConnectorBinding, ApplicationExtensionInstallation,
    ApplicationSecretReference, ModuleInstallation, ModulePackage,
)
from backend.services import application_authority_sources as sources
from backend.services.authority_metadata import (
    authority_transaction, read_connector_authority, read_device_control,
)
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_review import with_commands
from backend.tests.test_module_packages import application_package
from three_mm_protocol.node_features import MANDATORY_NODE_FEATURES


NOW = datetime.now(UTC)
DEVICE = "dev_" + "3" * 32
CREDENTIAL = "cred_" + "4" * 32
SECRET = "secret_" + "2" * 32
PRIVATE = "PRIVATE_MUST_NOT_APPEAR"
CONTRACT = {
    "schema_version": 1, "capability_id": "gpio.digital.control", "contract_version": "1.0",
    "actions": {"pulse": {"arguments_schema": {"type": "object", "properties": {},
        "additionalProperties": False}, "result_schema": {"type": "object", "properties": {},
        "additionalProperties": False}}},
}


@pytest.fixture
def installed(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'sources.db').as_posix()}", connect_args={"timeout": 3})
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    tables = (
        CoreAuthorityGuard, ModulePackage, ApplicationExtensionInstallation,
        ApplicationSecretReference, ApplicationConnectorBinding, CoreInstallationIdentity,
        Device, DeviceCredential, DevicePlatformState, DeviceRuntimeFeatures,
        ModuleInstallation, DeviceCapabilityProvider,
    )
    Base.metadata.create_all(engine, tables=[model.__table__ for model in tables])
    validated, configuration = with_commands()
    manifest = validated.manifest.model_dump(mode="json")
    manifest["configuration_schema"]["properties"]["PRIVATE_NOTE"] = {"type": "string"}
    configuration["PRIVATE_NOTE"] = PRIVATE
    definition = validated.application_extension.model_dump(mode="json")
    # This baseline tests command/connector sources. Positive event authority
    # uses a separately selected producer in test_application_event_authority.
    definition["event_subscriptions"] = []
    manifest["permissions"].remove("events.consume")
    blob = application_package(definition=definition, manifest_value=manifest)
    validated = validate_module_package(blob)
    root = tmp_path / "uploads"
    archive = root / "modules" / f"{validated.sha256}.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(blob)
    with Session(engine) as db, db.begin():
        db.add(CoreAuthorityGuard(singleton_id=1))
        raw_key = b"a" * 32
        db.add(CoreInstallationIdentity(singleton_id=1, installation_id="inst_" + "5" * 32,
            identity_version=1, key_generation=1, key_id=hashlib.sha256(raw_key).hexdigest(),
            public_key=base64.b64encode(raw_key).decode(), encrypted_private_key=PRIVATE, created_at=NOW))
        db.add(ModulePackage(id=1, module_id=validated.manifest.module_id, version="1.0.0",
            manifest=manifest, sha256=validated.sha256, size_bytes=len(blob), file_path=PRIVATE))
        db.flush()
        db.add(ApplicationExtensionInstallation(id=1, module_id=validated.manifest.module_id,
            module_package_id=1, instance_id="a" * 24, active_version="1.0.0", status="active",
            enabled=True, socket_path=PRIVATE, configuration=configuration))
        db.add(Device(id=1, device_id=DEVICE, role="standalone", protocol_version="1.0", approved_at=NOW))
        db.flush()
        db.add(DeviceCredential(device_id=1, credential_id=CREDENTIAL, secret_hash=PRIVATE))
        db.add(DevicePlatformState(device_id=1, authority_status="bound", lifecycle="active"))
        db.add(DeviceRuntimeFeatures(device_id=1, revision=7, received_at=NOW, declaration={
            "device_id": DEVICE, "runtime_name": "reference-runtime", "runtime_version": "1.0.0",
            "features": sorted(MANDATORY_NODE_FEATURES | {"application_execution_permits", "capability_contracts.v1"}),
            "command_types": ["capability.invoke", "application.capability.invoke"],
        }))
        db.add(DeviceCapabilityProvider(device_id=1, provider_type="native", provider_id="org.example.provider",
            provider_version="1.0.0", revision=8, enabled=True, reported_at=NOW,
            configured_capability_ids=["gpio.digital.control"], capabilities=[{
                "capability_id": "gpio.digital.control", "metadata": {}, "contract": CONTRACT,
            }]))
        db.add(ApplicationSecretReference(id=1, application_installation_id=1, secret_ref=SECRET,
            label=PRIVATE, credential_kind="basic", encrypted_value=PRIVATE, version=9))
        db.flush()
        db.add(ApplicationConnectorBinding(id=1, application_installation_id=1, connector_id="business_api",
            destination_origin=configuration["BUSINESS_API_URL"], secret_reference_id=1, enabled=True))
    state = SimpleNamespace(engine=engine, root=root, archive=archive, configuration=configuration,
        validated=validated)
    yield state
    engine.dispose()


def resolve(state):
    return sources.resolve_installed_authority_sources(state.engine, 1,
        uploads_root=state.root, core_version="0.3.0")


def reasons(result):
    return {item.reason for item in result.issues}


def replace_archive(state, *, definition=None, manifest=None, configuration=None):
    blob = application_package(
        definition=definition or state.validated.application_extension.model_dump(mode="json"),
        manifest_value=manifest or state.validated.manifest.model_dump(mode="json"),
    )
    package = validate_module_package(blob)
    archive = state.root / "modules" / f"{package.sha256}.zip"
    archive.write_bytes(blob)
    with Session(state.engine) as db, db.begin():
        db.execute(update(ModulePackage).where(ModulePackage.id == 1)
            .values(sha256=package.sha256, size_bytes=len(blob)))
        if configuration is not None:
            db.execute(update(ApplicationExtensionInstallation).values(configuration=configuration))


def test_real_sources_never_mint_policy_key_grant_or_reviewability(installed):
    result = resolve(installed)
    assert result.sources_resolved, result
    assert result.principal.core_installation_id == "inst_" + "5" * 32
    assert result.baseline.artifact.sha256 == installed.validated.sha256
    assert result.baseline.grant_revision is None and result.baseline.enforcement_mode == "compatibility"
    command = result.commands[0]
    assert command.target.device_id == DEVICE
    assert command.target.active_credential_ids == (CREDENTIAL,)
    assert command.target.runtime_revision == 7
    assert command.provider_type == "native" and len(command.contract_digest) == 64
    assert command.provider_revision == 8 and command.module_artifact_sha256 is None
    assert result.connectors[0].stored.credential.version == 9
    assert result.connectors[0].stored.credential.owner == result.principal
    assert {"configuration_key_unavailable", "policy_evidence_unavailable",
        "candidate_staging_not_implemented", "frontend_authority_unresolved",
        "unsupported_scope_family", "command_schema_containment_not_evaluated"} <= reasons(result)
    assert not result.reviewable and result.context_fingerprint is None
    assert result.permission_approval == "not_evaluated"
    assert PRIVATE not in result.model_dump_json() and PRIVATE not in repr(result)
    assert resolve(installed) == result


def test_disabled_installation_is_read_without_enabling_it(installed):
    with Session(installed.engine) as db, db.begin():
        db.execute(update(ApplicationExtensionInstallation).values(status="disabled", enabled=False))
    assert resolve(installed).sources_resolved
    with Session(installed.engine) as db:
        assert not db.get(ApplicationExtensionInstallation, 1).enabled


def test_new_install_is_unavailable_not_an_empty_approved_baseline(installed):
    with Session(installed.engine) as db, db.begin():
        db.execute(delete(ApplicationExtensionInstallation))
    result = resolve(installed)
    assert reasons(result) == {"installation_unavailable"} and result.baseline is None


def test_manifest_defaults_do_not_replace_missing_saved_device_binding(installed):
    manifest = installed.validated.manifest.model_dump(mode="json")
    manifest["configuration_defaults"]["TARGET_DEVICE_ID"] = DEVICE
    configuration = dict(installed.configuration)
    del configuration["TARGET_DEVICE_ID"]
    replace_archive(installed, manifest=manifest, configuration=configuration)
    assert reasons(resolve(installed)) == {"configuration_unresolved"}


def test_conflicting_capability_providers_are_not_resolved(installed):
    with Session(installed.engine) as db, db.begin():
        db.add(DeviceCapabilityProvider(device_id=1, provider_type="native", provider_id="org.example.other",
            provider_version="1.0.0", revision=1, enabled=True, reported_at=NOW,
            configured_capability_ids=["gpio.digital.control"], capabilities=[{
                "capability_id": "gpio.digital.control", "contract": CONTRACT,
            }]))
    assert reasons(resolve(installed)) == {"capability_unresolved"}


def test_sensor_identity_can_resolve_but_sensor_contract_is_not_inferred(installed):
    definition = installed.validated.application_extension.model_dump(mode="json")
    definition["command_bindings"][0].update(sensor_device_config_key="TARGET_DEVICE_ID", sensor_id="passage.1")
    replace_archive(installed, definition=definition)
    result = resolve(installed)
    assert result.sources_resolved and result.commands[0].sensor.device_id == DEVICE
    assert "sensor_contract_unresolved" in reasons(result) and not result.reviewable


def test_unauthenticated_connector_does_not_inherit_attached_credential(installed):
    definition = installed.validated.application_extension.model_dump(mode="json")
    definition["connectors"][0].update(authentication="none", credential_ref_config_key=None)
    manifest = installed.validated.manifest.model_dump(mode="json")
    manifest["permissions"].remove("secrets.use")
    replace_archive(installed, definition=definition, manifest=manifest)
    assert reasons(resolve(installed)) == {"connector_credential_unavailable"}
    with Session(installed.engine) as db, db.begin():
        db.execute(update(ApplicationConnectorBinding).values(secret_reference_id=None))
    result = resolve(installed)
    assert result.sources_resolved and result.connectors[0].stored.credential is None
    assert result.connectors[0].configured_secret_ref is None


def test_unsafe_origin_and_path_fail_without_returning_private_values(installed):
    configuration = {**installed.configuration,
        "BUSINESS_API_URL": f"https://user:{PRIVATE}@api.example.test/?token={PRIVATE}"}
    with Session(installed.engine) as db, db.begin():
        db.execute(update(ApplicationExtensionInstallation).values(configuration=configuration))
    result = resolve(installed)
    assert reasons(result) == {"connector_origin_mismatch"} and PRIVATE not in repr(result)
    definition = installed.validated.application_extension.model_dump(mode="json")
    definition["connectors"][0]["path_prefix"] = "/encoded%2fpath"
    replace_archive(installed, definition=definition, configuration=installed.configuration)
    assert reasons(resolve(installed)) == {"connector_path_unsupported"}


@pytest.mark.parametrize("role", ["standalone", "hub", "node"])
@pytest.mark.parametrize("provider", ["native", "embedded_firmware", "agent_module"])
def test_common_registry_and_roles_no_fleet_or_concrete_platform_dependency(installed, role, provider):
    with Session(installed.engine) as db, db.begin():
        db.execute(update(Device).values(role=role))
        if provider == "agent_module":
            db.execute(delete(DeviceCapabilityProvider))
            db.add(ModulePackage(id=2, module_id="org.example.provider", version="1.0.0", sha256="b" * 64,
                manifest={}, file_path=PRIVATE, size_bytes=1, registrations=[{
                    "kind": "capability", "registration_id": "gpio.digital.control", "metadata": {},
                    "contract": CONTRACT,
                }]))
            db.flush()
            db.add(ModuleInstallation(device_id=1, module_package_id=2, module_id="org.example.provider",
                desired_version="1.0.0", installed_version="1.0.0", enabled=True, status="succeeded"))
        else:
            db.execute(update(DeviceCapabilityProvider).values(provider_type=provider))
    result = resolve(installed)
    assert result.sources_resolved and result.commands[0].provider_type == provider
    if provider == "agent_module":
        assert result.commands[0].module_artifact_sha256 == "b" * 64
        assert result.commands[0].provider_revision is None
    assert not result.reviewable


@pytest.mark.parametrize("problem,reason", [
    ("guard", "source_unavailable"), ("identity", "identity_unavailable"),
    ("public_key", "identity_unavailable"), ("platform", "source_unavailable"),
    ("revoked_device", "device_unavailable"), ("released", "device_unavailable"),
    ("credential", "device_credentials_unavailable"), ("runtime", "runtime_support_unresolved"),
    ("provider_disabled", "capability_unresolved"), ("offer_only", "capability_unresolved"),
    ("wrong_contract", "command_contract_unresolved"), ("connector", "connector_binding_unavailable"),
    ("disabled_connector", "connector_binding_unavailable"), ("wrong_origin", "connector_origin_mismatch"),
    ("credential_kind", "connector_credential_unavailable"), ("secret_revoked", "connector_credential_unavailable"),
    ("wrong_reference", "connector_credential_unavailable"), ("foreign_secret", "connector_credential_unavailable"),
    ("configuration", "configuration_unresolved"), ("transition", "installation_unavailable"),
])
def test_missing_corrupt_foreign_or_unselected_sources_fail_closed(installed, problem, reason):
    with Session(installed.engine) as db, db.begin():
        if problem in {"guard", "identity", "platform", "runtime", "connector"}:
            model = {"guard": CoreAuthorityGuard, "identity": CoreInstallationIdentity,
                "platform": DevicePlatformState, "runtime": DeviceRuntimeFeatures,
                "connector": ApplicationConnectorBinding}[problem]
            db.execute(delete(model))
        elif problem == "public_key":
            db.execute(update(CoreInstallationIdentity).values(public_key="x" * 44))
        elif problem == "revoked_device":
            db.execute(update(Device).values(revoked_at=NOW))
        elif problem == "released":
            db.execute(update(DevicePlatformState).values(authority_status="released"))
        elif problem == "credential":
            db.execute(update(DeviceCredential).values(revoked_at=NOW))
        elif problem in {"provider_disabled", "offer_only", "wrong_contract"}:
            values = {"enabled": False} if problem == "provider_disabled" else {"configured_capability_ids": []}
            if problem == "wrong_contract":
                values = {"capabilities": [{"capability_id": "gpio.digital.control", "contract": {**CONTRACT, "contract_version": "2.0"}}]}
            db.execute(update(DeviceCapabilityProvider).values(**values))
        elif problem == "disabled_connector":
            db.execute(update(ApplicationConnectorBinding).values(enabled=False))
        elif problem == "wrong_origin":
            db.execute(update(ApplicationConnectorBinding).values(destination_origin="https://other.test"))
        elif problem == "credential_kind":
            db.execute(update(ApplicationSecretReference).values(credential_kind="bearer"))
        elif problem == "secret_revoked":
            db.execute(update(ApplicationSecretReference).values(revoked_at=NOW))
        elif problem == "foreign_secret":
            db.execute(update(ApplicationSecretReference).values(application_installation_id=2))
        elif problem in {"wrong_reference", "configuration"}:
            configuration = dict(installed.configuration)
            configuration["BUSINESS_API_CREDENTIAL" if problem == "wrong_reference" else "TARGET_DEVICE_ID"] = PRIVATE
            db.execute(update(ApplicationExtensionInstallation).values(configuration=configuration))
        elif problem == "transition":
            db.execute(update(ApplicationExtensionInstallation).values(status="activating"))
    result = resolve(installed)
    assert not result.sources_resolved and reasons(result) == {reason}, result
    assert result.guard is None and not result.commands and not result.connectors
    assert PRIVATE not in result.model_dump_json()


@pytest.mark.parametrize("problem", ["missing", "corrupt", "changed", "symlink"])
def test_artifact_read_is_pinned_bounded_and_redacted(installed, problem, tmp_path):
    if problem == "missing":
        installed.archive.unlink()
    elif problem == "symlink":
        foreign = tmp_path / PRIVATE
        foreign.write_bytes(installed.archive.read_bytes())
        installed.archive.unlink()
        installed.archive.symlink_to(foreign)
    else:
        installed.archive.write_bytes(PRIVATE.encode() if problem == "corrupt" else application_package())
    result = resolve(installed)
    assert reasons(result) == {"artifact_unavailable"}
    assert PRIVATE not in result.model_dump_json() and str(tmp_path) not in result.model_dump_json()


def test_package_validation_outside_snapshot_and_pointer_rechecked(installed, monkeypatch):
    read = sources._read_baseline

    def replace_after_read(*args):
        package = read(*args)
        # An independent writer commits while artifact processing is in progress.
        with Session(installed.engine) as db, db.begin():
            db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(sha256="f" * 64))
        return package

    monkeypatch.setattr(sources, "_read_baseline", replace_after_read)
    assert reasons(resolve(installed)) == {"artifact_changed"}


def test_no_flush_no_private_columns_no_network_execution_or_file_writes(installed, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("source resolver must not mutate, decrypt or execute")

    statements = []

    def check(_connection, _cursor, statement, *_args):
        statements.append(statement)
        assert statement.lstrip().upper().startswith(("SELECT", "BEGIN", "PRAGMA QUERY_ONLY", "PRAGMA READ_UNCOMMITTED")), statement
        assert all(name not in statement for name in ("encrypted_value", "secret_hash", "encrypted_private_key"))

    with Session(installed.engine) as caller:
        cached = caller.get(ApplicationExtensionInstallation, 1)
        cached.status = "activating"
        caller.add(ModulePackage(module_id="org.example.pending", version="1.0.0"))
        pending = tuple(caller.new)
        for name in ("flush", "commit", "add", "delete"):
            monkeypatch.setattr(Session, name, forbidden)
        for name in ("write_bytes", "write_text", "mkdir"):
            monkeypatch.setattr(Path, name, forbidden)
        monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
        monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
        event.listen(installed.engine, "before_cursor_execute", check)
        try:
            assert resolve(installed).sources_resolved
            assert tuple(caller.new) == pending and cached.status == "activating"
        finally:
            event.remove(installed.engine, "before_cursor_execute", check)
    assert statements


def test_snapshot_is_read_only_and_pool_can_write_after_failure(installed):
    with pytest.raises(OperationalError):
        with sources._read_snapshot(installed.engine) as db:
            db.execute(update(ApplicationSecretReference).values(version=100))
    with Session(installed.engine) as db, db.begin():
        assert db.scalar(select(ApplicationSecretReference.version)) == 9
        db.execute(update(ApplicationSecretReference).values(version=10))
    assert resolve(installed).connectors[0].stored.credential.version == 10


def test_real_writer_commit_does_not_mix_guard_and_resource_snapshots(installed):
    before = resolve(installed)
    errors, fired = [], False

    def concurrent_writer():
        try:
            with Session(installed.engine) as db:
                with authority_transaction(db) as mutation:
                    binding = read_connector_authority(db, installation_id=1, binding_id=1)
                    mutation.advance_connector_revision(binding)
                    mutation.advance_device_control(read_device_control(db, 1))
                    db.execute(update(ApplicationSecretReference).values(version=10))
        except BaseException as exc:
            errors.append(exc)

    def interleave(_connection, _cursor, statement, *_args):
        nonlocal fired
        if not fired and statement.lstrip().startswith("SELECT core_authority_guard.generation"):
            # after_cursor_execute: the reader has established its DB snapshot.
            fired = True
            worker = threading.Thread(target=concurrent_writer)
            worker.start()
            worker.join(timeout=5)
            assert not worker.is_alive(), "read snapshot must not take the mutation guard"

    event.listen(installed.engine, "after_cursor_execute", interleave)
    try:
        during = resolve(installed)
    finally:
        event.remove(installed.engine, "after_cursor_execute", interleave)
    assert fired and not errors
    assert during == before  # Not old guard + new credential/control generation.
    after = resolve(installed)
    assert after.guard.revision == before.guard.revision + 2
    assert after.baseline.authority_epoch != before.baseline.authority_epoch
    assert after.commands[0].target.control_generation != before.commands[0].target.control_generation
    assert after.connectors[0].stored.binding_revision != before.connectors[0].stored.binding_revision
    assert after.connectors[0].stored.credential.version == 10
    assert not after.reviewable


def test_shared_memory_or_session_inputs_cannot_reuse_callers_transaction(installed):
    memory = create_engine("sqlite:///:memory:")
    try:
        with pytest.raises(sources._Unavailable):
            with sources._read_snapshot(memory):
                pytest.fail("shared connection cannot be used")
        with Session(installed.engine) as db:
            result = sources.resolve_installed_authority_sources(db, 1,
                uploads_root=installed.root, core_version="0.3.0")
            assert reasons(result) == {"snapshot_backend_unsupported"}
    finally:
        memory.dispose()


def test_read_uncommitted_is_not_accepted_as_a_consistent_snapshot(installed):
    with installed.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA read_uncommitted=ON")
    assert reasons(resolve(installed)) == {"snapshot_backend_unsupported"}
    with installed.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA read_uncommitted=OFF")
    assert resolve(installed).sources_resolved


def test_missing_database_is_not_created_by_inspection(tmp_path):
    path = tmp_path / "missing.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        result = sources.resolve_installed_authority_sources(engine, 1,
            uploads_root=tmp_path, core_version="0.3.0")
        assert reasons(result) == {"snapshot_backend_unsupported"}
        assert not path.exists()
    finally:
        engine.dispose()


def test_postgresql_transaction_options_are_read_only_repeatable_read(monkeypatch):
    # Dialect API wiring only, NOT a live PostgreSQL isolation/concurrency proof.
    calls = []

    class Connection:
        def execution_options(self, **options):
            calls.append(options)
            return self

        def begin(self):
            calls.append("begin")

        def rollback(self):
            calls.append("rollback")

    @contextmanager
    def connect():
        yield Connection()

    engine = create_engine("sqlite:///unused.db")
    monkeypatch.setattr(engine, "dialect", SimpleNamespace(name="postgresql"))
    monkeypatch.setattr(engine, "connect", connect)
    monkeypatch.setattr(sources, "Session", lambda **kwargs: fake_session())

    @contextmanager
    def fake_session():
        calls.append("session")
        yield object()

    with sources._read_snapshot(engine):
        calls.append("read")
    assert calls == [{"isolation_level": "REPEATABLE READ", "postgresql_readonly": True},
        "begin", "session", "read", "rollback"]
