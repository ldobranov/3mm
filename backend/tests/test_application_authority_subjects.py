"""Real read-only subject composition; Linux key checks are not emulated."""

import copy
from datetime import UTC, datetime
import inspect
import io
import json
import os
from pathlib import Path
import threading
import zipfile

import pytest
import requests
from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session

from backend.db.authority import CoreAuthorityGuard
from backend.db.device import DeviceCapabilityProvider, DeviceCredential, DeviceRuntimeFeatures
from backend.db.module import ApplicationConnectorBinding, ApplicationExtensionInstallation, ApplicationSecretReference, ModulePackage
from backend.services import application_authority_keys as keys
from backend.services import application_authority_sources as sources
from backend.services import application_authority_subjects as subjects
from backend.services.application_authority_policy import evaluate_authority_policy
from backend.services.authority_metadata import authority_transaction, read_application_authority, read_connector_authority
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_authority_sources import (
    CONTRACT, DEVICE, PRIVATE, installed as source_installed, replace_archive,
)


posix_only = pytest.mark.skipif(os.name != "posix", reason="Requires real Core-owned POSIX key files")


@pytest.fixture
def installed(source_installed, tmp_path):
    state = source_installed
    state.key_directory = tmp_path / "authority-review"
    state.keys = keys.CoreReviewKeyStore(state.engine, state.key_directory)
    contract = copy.deepcopy(CONTRACT)
    contract["actions"]["pulse"]["arguments_schema"] = state.validated.application_extension.command_bindings[0].arguments_schema
    with state.engine.begin() as db:
        db.execute(update(DeviceCapabilityProvider).values(capabilities=[{
            "capability_id": "gpio.digital.control", "metadata": {}, "contract": contract}]))
    return state


def resolve(state):
    return subjects.resolve_installed_policy_subject(state.engine, 1,
        uploads_root=state.root, core_version="0.3.0", review_key_directory=state.key_directory)


def reasons(result):
    return {issue.reason for issue in result.issues}


def test_no_client_snapshot_or_implicit_key_creation(installed):
    signature = inspect.signature(subjects.resolve_installed_policy_subject)
    assert set(signature.parameters) == {"engine", "installation_id", "uploads_root", "core_version", "review_key_directory"}
    result = resolve(installed)
    assert result.subject is None and result.guard is None
    assert reasons(result) == {"configuration_key_unavailable"}
    assert not installed.key_directory.exists() and not result.reviewable


def test_exact_schema_comparison_is_typed_bounded_and_set_order_independent():
    schema = {"type": "object", "additionalProperties": False,
        "properties": {"v": {"type": "number", "minimum": 0, "maximum": 10, "enum": [1, 2]}}, "required": ["v"]}
    reordered = copy.deepcopy(schema)
    reordered["properties"]["v"]["enum"].reverse()
    assert subjects._schema_bytes(schema) == subjects._schema_bytes(reordered)
    for alternative in (1.0, True, "1"):
        changed = copy.deepcopy(schema)
        changed["properties"]["v"]["enum"][0] = alternative
        assert subjects._schema_bytes(changed) != subjects._schema_bytes(schema)
    changed = copy.deepcopy(schema)
    changed["properties"]["v"]["enum"] = [1, 1]
    with pytest.raises(ValueError):
        subjects._schema_bytes(changed)


@posix_only
def test_actual_subject_binds_saved_config_artifact_resources_and_real_key_without_authorizing(installed):
    key = installed.keys.provision()
    first = resolve(installed)
    subject = first.subject
    assert subject is not None, first
    assert subject.binding.candidate == subject.binding.baseline.artifact
    assert subject.binding.candidate.sha256 == installed.validated.sha256
    assert subject.binding.configuration == installed.keys.fingerprint(subject.binding.principal, installed.configuration)
    assert subject.binding.configuration.key_id == key.key_id
    assert subject.binding.recovery_generation == first.guard.generation
    assert subject.commands[0].target_device_id == DEVICE
    assert subject.commands[0].control_revision.startswith("control_")
    assert subject.connectors[0].stored.credential.version == 9
    assert subject.has_executable_frontend and "frontend_authority_unresolved" in subject.blockers
    assert "unsupported_scope_family" in subject.blockers
    assert "configuration_key_unavailable" not in reasons(first)
    assert "policy_evidence_unavailable" in reasons(first)
    assert first == resolve(installed) and not first.reviewable
    assert first.permission_approval == "not_evaluated"
    assert not evaluate_authority_policy(subject).policy_resolved
    assert PRIVATE not in first.model_dump_json() and PRIVATE not in repr(first)


@posix_only
def test_headless_command_connector_subject_still_requires_authentic_policy(installed):
    manifest = installed.validated.manifest.model_dump(mode="json")
    manifest.update(runtimes=["core"], entrypoints={"core": "application-extension.json"})
    manifest["capabilities"] = {"provides": [], "consumes": ["gpio.digital.control"]}
    manifest["permissions"] = [value for value in manifest["permissions"] if not value.startswith("events.")]
    definition = installed.validated.application_extension.model_dump(mode="json")
    definition.update(routes=[], event_subscriptions=[], jobs=[], permissions=[])
    definition["operations"] = [definition["operations"][0]]  # Private health only.
    output = io.BytesIO()
    with zipfile.ZipFile(installed.archive) as previous, zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        artifact = definition["service"]["artifact"]
        archive.writestr(artifact, previous.read(artifact))
    blob = output.getvalue()
    package = validate_module_package(blob)
    (installed.root / "modules" / f"{package.sha256}.zip").write_bytes(blob)
    with installed.engine.begin() as db:
        db.execute(update(ModulePackage).values(sha256=package.sha256, size_bytes=len(blob)))
    installed.keys.provision()
    result = resolve(installed)
    assert result.subject is not None, result
    assert not result.subject.has_executable_frontend and result.subject.blockers == ()
    assert result.subject.commands and result.subject.connectors
    assert reasons(result) == {"policy_evidence_unavailable"}
    assert not result.reviewable and not evaluate_authority_policy(result.subject).policy_resolved


@posix_only
def test_full_private_configuration_and_key_rotation_change_subject_identity(installed):
    original = installed.keys.provision()
    first = resolve(installed).subject
    with installed.engine.begin() as db:
        db.execute(update(ApplicationExtensionInstallation).values(configuration={
            **installed.configuration, "PRIVATE_NOTE": "ANOTHER_PRIVATE_VALUE"}))
    changed = resolve(installed).subject
    assert changed.binding.configuration != first.binding.configuration
    assert changed.commands == first.commands and changed.connectors == first.connectors
    installed.keys.rotate(expected_key_id=original.key_id)
    rotated = resolve(installed).subject
    assert rotated.binding.configuration != changed.binding.configuration
    assert rotated.binding.configuration.key_id != original.key_id
    assert "ANOTHER_PRIVATE_VALUE" not in rotated.model_dump_json()


@posix_only
@pytest.mark.parametrize("resource", ["device_credential", "provider", "runtime", "secret", "binding"])
def test_every_actual_control_or_connector_pin_affects_subject(installed, resource):
    installed.keys.provision()
    before = resolve(installed).subject
    with installed.engine.begin() as db:
        if resource == "device_credential":
            db.execute(update(DeviceCredential).values(credential_id="cred_" + "6" * 32))
        elif resource == "provider":
            db.execute(update(DeviceCapabilityProvider).values(revision=9))
        elif resource == "runtime":
            db.execute(update(DeviceRuntimeFeatures).values(revision=8))
        elif resource == "secret":
            db.execute(update(ApplicationSecretReference).values(version=10))
        else:
            db.execute(update(ApplicationConnectorBinding).values(authority_revision="7" * 32))
    after = resolve(installed).subject
    assert after is not None
    assert after != before
    if resource in {"device_credential", "provider", "runtime"}:
        assert after.commands[0].control_revision != before.commands[0].control_revision


@posix_only
@pytest.mark.parametrize("failure", ["stale_key", "foreign_key", "corrupt_key", "unsafe_key", "credential", "connector", "artifact"])
def test_missing_stale_foreign_corrupt_or_unowned_state_returns_no_partial_subject(installed, failure):
    installed.keys.provision()
    if failure in {"stale_key", "credential", "connector"}:
        with installed.engine.begin() as db:
            if failure == "stale_key":
                db.execute(update(CoreAuthorityGuard).values(generation="9" * 32))
            elif failure == "credential":
                db.execute(update(DeviceCredential).values(revoked_at=datetime.now(UTC)))
            else:
                db.execute(update(ApplicationConnectorBinding).values(application_installation_id=2))
    elif failure == "foreign_key":
        path = installed.key_directory / keys.KEY_NAME
        record = keys._decode(path.read_bytes())
        path.write_bytes(keys._encode(keys._KeyRecord(keys.ReviewKeyIdentity(record.identity.key_id,
            keys.ReviewKeyBinding("inst_" + "9" * 32, record.identity.binding.recovery_generation)), record.secret)))
    elif failure == "corrupt_key":
        (installed.key_directory / keys.KEY_NAME).write_bytes(PRIVATE.encode())
    elif failure == "unsafe_key":
        (installed.key_directory / keys.KEY_NAME).chmod(0o644)
    else:
        installed.archive.write_bytes(PRIVATE.encode())
    result = resolve(installed)
    assert result.subject is None and result.guard is None and not result.reviewable
    assert PRIVATE not in result.model_dump_json()


@pytest.mark.parametrize("kind", ["wider", "narrower", "sensor"])
def test_unsupported_command_is_not_omitted_or_implicitly_approved(installed, kind):
    definition = installed.validated.application_extension.model_dump(mode="json")
    if kind == "sensor":
        definition["command_bindings"][0].update(sensor_device_config_key="TARGET_DEVICE_ID", sensor_id="passage.1")
    else:
        definition["command_bindings"][0]["arguments_schema"]["properties"]["duration_ms"]["maximum"] = (
            500 if kind == "wider" else 100)
    replace_archive(installed, definition=definition)
    result = resolve(installed)
    assert result.subject is None and result.guard is None
    assert reasons(result) == {"sensor_contract_unresolved" if kind == "sensor" else "command_schema_containment_not_evaluated"}


@posix_only
def test_artifact_validation_is_outside_snapshot_and_new_pin_is_rejected(installed, monkeypatch):
    installed.keys.provision()
    original = sources._read_baseline

    def drift(*args):
        package = original(*args)
        with installed.engine.begin() as db:
            db.execute(update(ModulePackage).values(sha256="f" * 64))
        return package

    monkeypatch.setattr(sources, "_read_baseline", drift)
    assert reasons(resolve(installed)) == {"artifact_changed"}


@posix_only
def test_actual_writer_interleaving_does_not_mix_config_resources_key_and_guard(installed):
    installed.keys.provision()
    before = resolve(installed)
    fired, failures = False, []

    def writer():
        try:
            with Session(installed.engine) as db, authority_transaction(db) as mutation:
                application = read_application_authority(db, 1)
                mutation.advance_application_epoch(application)
                mutation.advance_connector_revision(read_connector_authority(db, installation_id=1, binding_id=1))
                db.execute(update(ApplicationExtensionInstallation).values(configuration={
                    **installed.configuration, "PRIVATE_NOTE": "NEW_PRIVATE_VALUE"}))
                db.execute(update(ApplicationSecretReference).values(version=10))
        except BaseException as exc:
            failures.append(exc)

    def interleave(_conn, _cursor, statement, *_args):
        nonlocal fired
        if not fired and statement.startswith("SELECT core_authority_guard.generation"):
            fired = True
            worker = threading.Thread(target=writer)
            worker.start()
            worker.join(5)
            assert not worker.is_alive()

    event.listen(installed.engine, "after_cursor_execute", interleave)
    try:
        during = resolve(installed)
    finally:
        event.remove(installed.engine, "after_cursor_execute", interleave)
    assert fired and not failures and during == before
    after = resolve(installed)
    assert after.guard != before.guard
    assert after.subject.binding.configuration != before.subject.binding.configuration
    assert after.subject.binding.baseline.authority_epoch != before.subject.binding.baseline.authority_epoch
    assert after.subject.connectors[0].stored.credential.version == 10


@posix_only
def test_no_mutation_private_db_columns_network_code_or_external_session_cache(installed, monkeypatch):
    installed.keys.provision()

    def forbidden(*_args, **_kwargs):
        pytest.fail("subject composition must remain read-only")

    statements = []

    def check(_conn, _cursor, statement, *_args):
        statements.append(statement)
        assert statement.lstrip().upper().startswith(("SELECT", "BEGIN", "PRAGMA QUERY_ONLY", "PRAGMA READ_UNCOMMITTED"))
        assert all(value not in statement for value in ("secret_hash", "encrypted_value", "encrypted_private_key"))

    content = (installed.key_directory / keys.KEY_NAME).read_bytes()
    with Session(installed.engine) as caller:
        cached = caller.get(ApplicationExtensionInstallation, 1)
        cached.configuration = {"PRIVATE_NOTE": "PENDING_PRIVATE_VALUE"}
        for name in ("add", "delete", "flush", "commit"):
            monkeypatch.setattr(Session, name, forbidden)
        for name in ("write_bytes", "write_text", "mkdir"):
            monkeypatch.setattr(Path, name, forbidden)
        monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
        event.listen(installed.engine, "before_cursor_execute", check)
        try:
            result = resolve(installed)
            assert result.subject is not None and cached in caller.dirty
            assert "PENDING_PRIVATE_VALUE" not in result.model_dump_json()
        finally:
            event.remove(installed.engine, "before_cursor_execute", check)
    assert statements and (installed.key_directory / keys.KEY_NAME).read_bytes() == content


@posix_only
def test_protected_key_is_locked_during_fingerprint_and_other_db_is_refused(installed, monkeypatch):
    key = installed.keys.provision()
    original = keys._configuration_identity

    def under_lock(*args):
        with pytest.raises(keys.AuthorityReviewKeyError):
            installed.keys.rotate(expected_key_id=key.key_id)
        return original(*args)

    monkeypatch.setattr(keys, "_configuration_identity", under_lock)
    assert resolve(installed).subject is not None
    assert installed.keys.identity() == key
    other = create_engine(installed.engine.url)
    try:
        foreign_store = keys.CoreReviewKeyStore(other, installed.key_directory)
        with sources._read_snapshot(installed.engine) as db:
            db.execute(CoreAuthorityGuard.__table__.select()).first()
            with pytest.raises(keys.AuthorityReviewKeyError):
                foreign_store._fingerprint_in_snapshot(db, {}, {})
    finally:
        other.dispose()


@pytest.mark.skipif(os.name == "posix", reason="Real non-POSIX refusal")
def test_non_posix_never_invents_a_configuration_identity(installed):
    assert reasons(resolve(installed)) == {"configuration_key_unavailable"}
    assert not installed.key_directory.exists()
