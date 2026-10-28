"""First vertical: real consent, signed SDK socket, two simulated providers.

Only provider effects are simulated. Declarations, DB snapshots, resource pins,
grants, current logins, SDK wire, queue, one-use permits and journals are real.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
import io
import zipfile
import hashlib
import subprocess
import sys
import time

import backend.database
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.orm import Session, sessionmaker

from agent.physical_command_journal import PhysicalCommandJournal
from backend.db.base import Base
from backend.db.device import (
    Device, DeviceCapabilityProvider, DeviceCapabilityHealth, DeviceCommand,
    DeviceCredential, DeviceHeartbeat, DevicePlatformState, DeviceRuntimeFeatures,
)
from backend.db.module import ApplicationExtensionInstallation as Installation, ModulePackage
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant
from backend.routes.application_extensions import router
from backend.services.application_command_discovery import discover_candidates
from backend.services.application_commands import authorize_execution
from backend.services import application_consent
from backend.services.module_packages import validate_module_package
from backend.services.application_authority_keys import KEY_NAME
from backend.services.application_platform import CoreRuntimeAuthorityServer
from backend.services.device_commands import command_envelope, deliver_next_command, record_command_result
from backend.services.device_capability_registry import capability_catalog, replace_provider
from backend.services.application_authority_sources import _read_snapshot
from backend.tests.test_application_authority_management import (
    installed, source_subject, source_installed, identity,
)
from backend.tests.test_application_consent import allow, preview
from backend.utils.db_utils import get_db
from examples.command_probe import CommandProbe
from three_mm_application_sdk import ApplicationPlatformClient, ApplicationPlatformError
from three_mm_protocol import CapabilityProviderReportV1
from three_mm_runtime.application_activation import application_instance_id
from three_mm_runtime.update_helper_client import UpdateHelperClient
from deployment.platform_runtime_component import build_component, validate_artifact
from three_mm_platform_runtime.server import probe_runtime

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX sealed grants and Unix sockets")


@pytest.fixture
def vertical(installed, monkeypatch):
    s = installed
    Base.metadata.create_all(s.engine)
    monkeypatch.setattr(backend.database, "SessionLocal", sessionmaker(bind=s.engine))
    app = FastAPI()
    app.include_router(router)
    from backend.routes.application_authority import router as authority_router
    app.include_router(authority_router)

    def database():
        with Session(s.engine) as db:
            yield db

    app.dependency_overrides[get_db] = database
    s.url = f"/api/v1/application-extensions/packages/{s.validated.sha256}/command-bindings/pulse/discovery"
    s.headers = {"Authorization": "Bearer " + s.token}
    with tempfile.TemporaryDirectory(prefix="3mm-discovery-") as directory, TestClient(app) as http:
        root = Path(directory)
        secret = b"s" * 32
        (root / ("a" * 24 + ".key")).write_bytes(secret)
        s.server = CoreRuntimeAuthorityServer(root / "authority.sock", root,
            runtime_uid=os.geteuid(), group="missing-test-group")
        s.server.start()
        blob, metadata = build_component(Path(__file__).resolve().parents[2])
        _, code = validate_artifact(blob, hashlib.sha256(blob).hexdigest())
        executable = root / "runtime.pyz"
        executable.write_bytes(code)
        s.runtime_socket = root / "runtime.sock"
        runtime = subprocess.Popen([sys.executable, "-I", str(executable),
            "--socket", str(s.runtime_socket), "--authority-socket", str(s.server.socket_path),
            "--core-uid", str(os.geteuid())], cwd=root,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    probe_runtime(s.runtime_socket, expected_uid=os.geteuid(), expected_build=metadata["build_id"])
                    break
                except (OSError, ValueError):
                    assert runtime.poll() is None and time.monotonic() < deadline
                    time.sleep(.01)
            s.sdk = ApplicationPlatformClient(s.runtime_socket, "a" * 24, secret)
            s.probe = CommandProbe(s.sdk, "pulse")
            s.http = http
            yield s
        finally:
            runtime.terminate()
            try:
                runtime.wait(timeout=3)
            except subprocess.TimeoutExpired:
                runtime.kill()
                runtime.wait(timeout=3)
            runtime.stderr.close()
            s.server.stop()


def candidates(s, **params):
    response = s.http.get(s.url, headers=s.headers, params=params)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def add_provider(s, *, device_id="dev_" + "6" * 32, smaller=False):
    with Session(s.engine) as db:
        source = db.scalar(select(DeviceCapabilityProvider).where(DeviceCapabilityProvider.device_id == 1))
        offered = deepcopy(source.capabilities)
        if smaller:
            offered[0]["contract"]["actions"]["pulse"]["arguments_schema"]["properties"]["duration_ms"]["maximum"] = 10
        features = deepcopy(db.scalar(select(DeviceRuntimeFeatures).where(DeviceRuntimeFeatures.device_id == 1)).declaration)
        features["device_id"] = device_id
        device = Device(device_id=device_id, role="node", protocol_version="1.0", approved_at=datetime.now(UTC))
        db.add(device)
        db.flush()
        numeric_id = device.id
        db.add_all([
            DeviceCredential(device_id=numeric_id, credential_id="cred_" + device_id[4:], secret_hash="test-only"),
            DevicePlatformState(device_id=numeric_id, authority_status="bound", lifecycle="active"),
            DeviceRuntimeFeatures(device_id=numeric_id, revision=1, received_at=datetime.now(UTC), declaration=features),
            DeviceHeartbeat(device_id=numeric_id, protocol_version="1.0", payload={}, received_at=datetime.now(UTC)),
        ])
        db.commit()
        replace_provider(db, device, CapabilityProviderReportV1.model_validate({
            "schema_version": 1, "device_id": device_id, "provider_type": "embedded_firmware",
            "provider_id": "org.example.second", "provider_version": "1.0.0",
            "expected_revision": 0, "capabilities": offered,
        }))
        row = capability_catalog(db, device)[0]
        db.add(DeviceCapabilityHealth(device_id=numeric_id, provider_type=row.provider_type,
            provider_id=row.provider_id, observed_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=5), report={
                "declaration_digest": row.declaration_digest,
                "capabilities": [{"capability_id": row.capability_id, "healthy": True}]}))
        db.commit()
    return numeric_id, device_id


def execute(s, directory, device_id, effects):
    with Session(s.engine) as db:
        device = db.get(Device, device_id)
        command = deliver_next_command(db, device=device)
        assert command is not None
        envelope = command_envelope(command, device.device_id)
        journal = PhysicalCommandJournal(directory)

        def invoke():
            effects.append(device.device_id)
            return {}

        result = journal.execute(envelope, invoke,
            authorize=lambda: authorize_execution(db, device, command.command_id))
        record_command_result(db, device=device, result=result)
        return envelope, result


def test_full_path_second_provider_selection_restart_and_no_replay(vertical, tmp_path):
    s = vertical
    initial = candidates(s)
    assert len(initial["candidates"]) == 1
    first = initial["candidates"][0]
    assert first["compatible"] and first["selectable"] and first["readiness"] == "ready"
    assert initial["access"] == "not_evaluated"
    assert s.probe.observe()["access"] == "required"
    allow(s, preview(s), scopes=["command:pulse"])
    assert s.probe.observe()["selected_device_id"] == first["device_id"]
    queued = s.probe.submit(request_id="first", arguments={"channel": "output.1", "duration_ms": 50})
    assert queued["status"] == "queued"
    effects = []
    envelope, result = execute(s, tmp_path / "first-provider", 1, effects)
    assert result.status == "succeeded" and effects == [first["device_id"]]
    # A fresh provider journal object and a restarted Core socket preserve receipts.
    recovered = PhysicalCommandJournal(tmp_path / "first-provider").execute(
        envelope, lambda: pytest.fail("Completed work replayed"))
    assert recovered == result
    s.server.stop()
    s.server.start()
    assert s.probe.lookup("first")["command"]["status"] == "succeeded"
    assert s.probe.observe()["selected_device_id"] == first["device_id"]

    add_provider(s)
    discovered = candidates(s)
    assert len(discovered["candidates"]) == 2
    assert all(item["selectable"] for item in discovered["candidates"])
    assert s.probe.observe()["selected_device_id"] == first["device_id"]
    assert len(s.probe.observe()["candidates"]) == 1  # No global inventory to SDK.


def test_requirement_summary_uses_real_runtime_grants_and_selected_provider_only(vertical):
    s = vertical
    needs = [
        {'requirement_id':'output', 'operations':['command.discover','command.submit'], 'binding_id':'pulse'},
        {'requirement_id':'optional_future', 'operations':['future.not_implemented'], 'required':False},
    ]
    blocked = s.sdk.discover_requirements(needs)
    assert blocked['status'] == 'blocked'
    assert blocked['requirements'][0]['command'] is None  # No scoped authority yet.
    allow(s, preview(s), scopes=['command:pulse'])
    add_provider(s)
    writes = []
    def trace(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE')):
            writes.append(statement)
    event.listen(s.engine, 'before_cursor_execute', trace)
    try:
        ready = s.sdk.discover_requirements(needs)
    finally:
        event.remove(s.engine, 'before_cursor_execute', trace)
    assert ready['status'] == 'degraded' and ready['requirements'][0]['met'] is True
    command = ready['requirements'][0]['command']
    assert command['selected_device_id'] == s.configuration['TARGET_DEVICE_ID']
    assert len(command['candidates']) == 1 and not writes
    with s.engine.begin() as db:
        db.execute(update(DeviceCapabilityHealth).where(DeviceCapabilityHealth.device_id==1).values(
            expires_at=datetime.now(UTC)-timedelta(seconds=1)))
    stale = s.sdk.discover_requirements(needs)
    assert stale['status'] == 'blocked'
    assert stale['requirements'][0]['reason'] == 'resource_unknown'
    assert stale['requirements'][0]['command']['access'] == 'granted'
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status['grant_record_revision'])
    denied = s.sdk.discover_requirements(needs)
    assert denied['status'] == 'blocked'
    assert denied['requirements'][0]['reason'] == 'scoped_authority_required'
    assert denied['requirements'][0]['command'] is None


@pytest.mark.parametrize("choose_second", [False, True])
def test_fresh_install_selects_either_provider_through_existing_admin_api(vertical, monkeypatch, tmp_path, choose_second):
    s = vertical
    second_id, second = add_provider(s)
    target = second if choose_second else s.configuration["TARGET_DEVICE_ID"]
    module_id = "org.example.command-probe"
    definition = s.validated.application_extension.model_dump(mode="json")
    definition.update(module_id=module_id, connectors=[])
    manifest = s.validated.manifest.model_dump(mode="json")
    manifest.update(module_id=module_id,
        permissions=["data.read", "data.write", "process.spawn", "capabilities.invoke"],
        configuration_schema={"type": "object", "additionalProperties": False,
            "properties": {"TARGET_DEVICE_ID": {"type": "string"}}})
    output = io.BytesIO()
    with zipfile.ZipFile(s.archive) as old, zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("application-extension.json", json.dumps(definition))
        archive.writestr(definition["service"]["artifact"], old.read(definition["service"]["artifact"]))
    package = validate_module_package(output.getvalue())
    path = s.root / "modules" / (package.sha256 + ".zip")
    path.write_bytes(output.getvalue())
    with Session(s.engine) as db, db.begin():
        db.add(ModulePackage(module_id=module_id, version="1.0.0", manifest=manifest,
            sha256=package.sha256, size_bytes=len(output.getvalue()), file_path=str(path)))
    base = f"/api/v1/application-extensions/packages/{package.sha256}"
    observed = s.http.get(base + "/command-bindings/pulse/discovery", headers=s.headers)
    assert observed.status_code == 200, observed.text
    assert observed.json()["selected_device_id"] is None
    assert len(observed.json()["candidates"]) == 2
    instance = application_instance_id(module_id)
    helper_calls = []

    def start_helper(_self, digest, actor_id, configuration, lifecycle):
        # The external systemd installer is simulated, not the Core transition.
        assert digest == package.sha256 and actor_id == 1
        assert configuration == {"TARGET_DEVICE_ID": target}
        helper_calls.append(configuration)
        return {"module_id": module_id, "version": "1.0.0", "sha256": digest,
                "instance_id": instance, "socket_path": "probe.sock"}

    monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", start_helper)
    denied = s.http.post(base + "/activate", headers={"Authorization": "Bearer " + s.user_token},
        json={"configuration": {"TARGET_DEVICE_ID": target}})
    assert denied.status_code == 403 and not helper_calls
    activated = s.http.post(base + "/activate", headers=s.headers,
        json={"configuration": {"TARGET_DEVICE_ID": target}})
    assert activated.status_code == 200, activated.text
    with Session(s.engine) as db:
        installation = db.scalar(select(Installation).where(Installation.module_id == module_id))
        installation_id = installation.id
        assert installation.configuration == {"TARGET_DEVICE_ID": target}
        assert installation.authority_mode == "review_required"
    secret = b"p" * 32
    (s.server.key_root / (instance + ".key")).write_bytes(secret)
    probe = CommandProbe(ApplicationPlatformClient(s.runtime_socket, instance, secret), "pulse")
    assert probe.observe()["access"] == "required"
    reviewed = application_consent.preview(s.manager, installation_id, actor_token=s.token, request_id=identity())
    application_consent.allow(s.manager, installation_id, actor_token=s.token, request_id=identity(),
        preview_id=reviewed["preview_id"], expected_revision=reviewed["revision"], fingerprint=reviewed["fingerprint"],
        scopes=["command:pulse"], user_permissions=[], accept_native_code=True)
    assert probe.observe()["selected_device_id"] == target
    assert s.probe.observe()["access"] == "required"  # Another app does not inherit consent.
    assert probe.submit(request_id="chosen", arguments={"channel": "output.1", "duration_ms": 50})["status"] == "queued"
    effects = []
    _, result = execute(s, tmp_path / "chosen-provider", second_id if choose_second else 1, effects)
    assert result.status == "succeeded" and effects == [target]
    assert probe.lookup("chosen")["command"]["status"] == "succeeded"


def test_admin_and_sdk_discovery_are_read_only_and_do_not_create_a_key(vertical):
    s = vertical
    (s.key_directory / KEY_NAME).unlink()
    writes = []

    def trace(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE")):
            writes.append(statement)

    event.listen(s.engine, "before_cursor_execute", trace)
    try:
        assert candidates(s)["candidates"][0]["selectable"]
        assert s.probe.observe()["access"] == "required"
    finally:
        event.remove(s.engine, "before_cursor_execute", trace)
    assert writes == [] and not (s.key_directory / KEY_NAME).exists()
    with Session(s.engine) as db:
        assert db.get(Grant, 1) is None


def test_denied_and_undeclared_discovery_never_reveals_resources(vertical):
    s = vertical
    assert s.http.get(s.url).status_code == 401
    assert s.http.get(s.url, headers={"Authorization": "Bearer " + s.user_token}).status_code == 403
    assert s.http.get(s.url, headers=s.headers, params={"after_device_id": "bad"}).status_code == 400
    denied = s.probe.observe()
    assert denied["selected_device_id"] is None and denied["candidates"] == []
    with pytest.raises(ApplicationPlatformError):
        s.sdk.discover_command("undeclared")
    with pytest.raises(ApplicationPlatformError):
        s.sdk._call("command.discover", {"binding_id": "pulse", "device_id": "dev_" + "3" * 32})
    assert "PRIVATE_MUST_NOT_APPEAR" not in json.dumps(candidates(s))


def test_incompatible_limits_and_unknown_health_have_distinct_reasons(vertical):
    s = vertical
    _, smaller = add_provider(s, smaller=True)
    observed = candidates(s)
    mismatch = next(item for item in observed["candidates"] if item["device_id"] == smaller)
    assert not mismatch["compatible"] and not mismatch["selectable"]
    assert "command_schema_containment_not_evaluated" in mismatch["blockers"]
    allow(s, preview(s), scopes=["command:pulse"])
    with s.engine.begin() as db:
        db.execute(update(DeviceCapabilityHealth).where(DeviceCapabilityHealth.device_id == 1).values(
            expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    current = s.probe.observe()
    assert current["access"] == "granted" and current["selected_device_id"] == observed["selected_device_id"]
    assert current["candidates"][0]["readiness"] == "unknown"
    assert current["candidates"][0]["readiness_reason"] == "health_stale"
    assert s.probe.submit(request_id="stale", arguments={"channel": "output.1", "duration_ms": 50})["status"] == "not_submitted"


@pytest.mark.parametrize("fault", ["revoked", "offline", "provider_changed", "disabled"])
def test_conditions_are_rechecked_after_discovery_before_effect(vertical, tmp_path, fault):
    s = vertical
    allow(s, preview(s), scopes=["command:pulse"])
    selected = s.probe.observe()["selected_device_id"]
    add_provider(s)
    s.sdk.submit_command("pulse", request_id="pending", arguments={"channel": "output.1", "duration_ms": 50}, ttl_seconds=5)
    with Session(s.engine) as db:
        device = db.get(Device, 1)
        queued = deliver_next_command(db, device=device)
        envelope = command_envelope(queued, device.device_id)
    if fault == "revoked":
        status = s.manager.inspect(1)
        s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status["grant_record_revision"])
    else:
        with s.engine.begin() as db:
            if fault == "offline":
                db.execute(update(DeviceHeartbeat).where(DeviceHeartbeat.device_id == 1).values(
                    received_at=datetime.now(UTC) - timedelta(days=1)))
            elif fault == "provider_changed":
                db.execute(update(DeviceCapabilityProvider).where(DeviceCapabilityProvider.device_id == 1).values(revision=9))
            else:
                db.execute(update(Installation).where(Installation.id == 1).values(enabled=False, status="disabled"))
    with Session(s.engine) as db:
        result = PhysicalCommandJournal(tmp_path / "denied").execute(envelope,
            lambda: pytest.fail("A stale observation authorized an effect"),
            authorize=lambda: authorize_execution(db, db.get(Device, 1), queued.command_id))
        assert result.status == "failed" and result.output["execution_state"] == "not_executed"
        assert db.get(Installation, 1).configuration["TARGET_DEVICE_ID"] == selected
        assert len(db.scalars(select(DeviceCommand)).all()) == 1
    if fault != "disabled":
        observed = s.probe.observe()
        if fault == "offline":
            assert observed["selected_device_id"] == selected
            assert observed["candidates"][0]["readiness_reason"] == "device_offline"
        else:
            assert observed["access"] == "required" and observed["candidates"] == []


def test_admin_discovery_obeys_database_read_only_snapshot(vertical):
    s = vertical
    with _read_snapshot(s.engine) as db:
        result = discover_candidates(db, s.validated.application_extension, "pulse")
    assert result["candidates"][0]["selectable"]

    allow(s, preview(s), scopes=["command:pulse"])
    writes = []

    def trace(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE")):
            writes.append(statement)

    event.listen(s.engine, "before_cursor_execute", trace)
    try:
        assert s.probe.observe()["access"] == "granted"
    finally:
        event.remove(s.engine, "before_cursor_execute", trace)
    assert writes == []


def test_discovery_is_scoped_to_the_selected_permission(vertical):
    s = vertical
    allow(s, preview(s), scopes=["connector:business_api"])
    observed = s.probe.observe()
    assert observed["access"] == "required" and observed["candidates"] == []


def test_candidate_pages_are_bounded_and_preserve_an_off_page_selection(vertical):
    s = vertical
    with Session(s.engine) as db, db.begin():
        for index in range(34):
            db.add(Device(device_id="dev_" + format(index, "032x"), role="node", protocol_version="1.0",
                approved_at=datetime.now(UTC)))
    first = candidates(s)
    assert len(first["candidates"]) == 32 and first["next_after_device_id"]
    second = candidates(s, after_device_id=first["next_after_device_id"])
    assert len(second["candidates"]) == 3 and second["next_after_device_id"] is None
    assert first["selected_device_id"] == second["selected_device_id"] == s.configuration["TARGET_DEVICE_ID"]
    assert not ({item["device_id"] for item in first["candidates"]} &
                {item["device_id"] for item in second["candidates"]})


def test_snapshot_cannot_be_used_to_submit_after_revocation(vertical):
    s = vertical
    allow(s, preview(s), scopes=["command:pulse"])
    assert s.probe.observe()["access"] == "granted"
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status["grant_record_revision"])
    with pytest.raises(ApplicationPlatformError):
        s.sdk.submit_command("pulse", request_id="revoked", arguments={"channel": "output.1", "duration_ms": 50}, ttl_seconds=5)
    with Session(s.engine) as db:
        assert db.scalar(select(DeviceCommand.id)) is None
