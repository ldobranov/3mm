"""Packaged operator application -> signed Runtime SDK -> two mock providers."""
from datetime import UTC, datetime, timedelta
import importlib.util
import hashlib
import os
from pathlib import Path
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from agent.hardware import MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from agent.physical_command_journal import PhysicalCommandJournal
from backend.db.device import Device, DeviceCapabilityHealth, DeviceCapabilityProvider, DeviceCommand
from backend.db.module import ApplicationExtensionInstallation as Installation, ApplicationPermissionGrant, ModulePackage
from backend.db.session import UserSession
from backend.config import ApplicationRuntimeSettings
from backend.routes import application_extensions as routes
from backend.services.application_commands import authorize_execution
from backend.services import compiled_ui, application_extensions as gateway, application_command_rebinding as rebind
from backend.services.device_capability_registry import capability_catalog
from backend.services.device_commands import command_envelope, deliver_next_command, record_command_result
from backend.services.module_packages import validate_module_package
from backend.tests.test_application_command_discovery import installed, source_subject, source_installed, vertical, add_provider, identity
from backend.tests.test_application_consent import allow, preview
from backend.tests.response_helpers import install_response_transport
from three_mm_application_sdk import OperationContext, ApplicationPlatformError
from three_mm_runtime.application_transport import ApplicationTransportError
from three_mm_runtime.application_host import _load_service
from three_mm_runtime.update_helper_client import UpdateHelperClient
from three_mm_runtime import application_lifecycle as helper_fencing

pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real POSIX native approval and signed Runtime sockets")


def builder(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def button(vertical, monkeypatch, tmp_path):
    s = vertical
    s.button_builder = builder("button_builder", "modules/command-probe/build_package.py")
    blob = s.button_builder.build_package()
    assert blob == s.button_builder.build_package()
    s.validated = validate_module_package(blob)
    s.archive = s.root / "modules" / (s.validated.sha256 + ".zip")
    s.archive.write_bytes(blob)
    output = builder("digital_builder", "modules/digital-output/build_package.py")
    s.output_blob = output.build_package(versioned=True)
    contract = output.versioned_manifest()["registrations"][0]["contract"]
    s.configuration = {"OUTPUT_DEVICE_ID": "dev_" + "3" * 32}
    with s.engine.begin() as db:
        db.execute(update(ModulePackage).where(ModulePackage.id == 1).values(module_id=s.validated.manifest.module_id,
            version=s.validated.manifest.version, manifest=s.validated.manifest.model_dump(mode="json"),
            sha256=s.validated.sha256, size_bytes=len(blob), file_path=str(s.archive)))
        db.execute(update(Installation).where(Installation.id == 1).values(module_id=s.validated.manifest.module_id,
            active_version=s.validated.manifest.version, configuration=s.configuration))
        db.execute(update(DeviceCapabilityProvider).values(provider_type="native", provider_id="org.example.first",
            capabilities=[{"capability_id": "gpio.digital.control", "metadata": {}, "contract": contract}]))
        db.execute(delete(DeviceCapabilityHealth))
    with Session(s.engine) as db, db.begin():
        offer = capability_catalog(db, db.get(Device, 1))[0]
        db.add(DeviceCapabilityHealth(device_id=1, provider_type=offer.provider_type, provider_id=offer.provider_id,
            observed_at=datetime.now(UTC), expires_at=datetime.now(UTC) + timedelta(minutes=5), report={
                "declaration_digest": offer.declaration_digest,
                "capabilities": [{"capability_id": offer.capability_id, "healthy": True}]}))
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    monkeypatch.setenv("COMPILED_UI_COMPILER_SCRIPT", str(frontend / "compiler/compile-ui-extension.mjs"))
    monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(s.root / "compiled"))
    s.build = compiled_ui.compile_ui_package(blob, s.validated)
    allow(s, preview(s), scopes=["command:output"], user_permissions=["control_output"])
    with Session(s.engine) as db, db.begin():
        db.add(ApplicationPermissionGrant(application_installation_id=1, user_id=2, permission_id="control_output"))
    instance = tmp_path / "button-instance"
    release = instance / "releases" / s.validated.sha256
    release.mkdir(parents=True)
    definition = s.validated.application_extension
    wheel = Path(definition.service.artifact).name
    with zipfile.ZipFile(s.archive) as archive:
        (release / wheel).write_bytes(archive.read(definition.service.artifact))
    metadata = {"module_id": s.validated.manifest.module_id, "version": s.validated.manifest.version,
        "sha256": s.validated.sha256, "wheel": wheel, "entrypoint": definition.service.entrypoint,
        "storage": definition.storage.model_dump(mode="json"), "configuration": s.configuration,
        "platform_socket": str(s.runtime_socket), "instance_id": "a" * 24}
    s.service = _load_service(metadata, instance, b"s" * 32)
    assert s.service.handle("health", {}, OperationContext("internal", "health")) == {"status": "ready"}
    s.operator = OperationContext("operator", "button", user_id=2)
    s.drivers = {}; s.agents = {}; s.journals = {}
    def agent(device_id):
        driver = MockDigitalGpioDriver()
        runtime = AgentModuleRuntime(tmp_path / f"agent-{device_id}", architecture="x86_64",
            runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(driver)})
        runtime.install(s.output_blob, expected_sha256=hashlib.sha256(s.output_blob).hexdigest())
        s.drivers[device_id] = driver; s.agents[device_id] = runtime
        s.journals[device_id] = PhysicalCommandJournal(tmp_path / f"journal-{device_id}")
    s.add_agent = agent
    agent(1)
    s.ui = {"host_version": 1, "entrypoint_id": "button", "artifact_sha256": s.validated.sha256,
        "built_ui_sha256": s.build.built_ui_sha256}
    s.base = f"/api/v1/application-extensions/{s.validated.manifest.module_id}"
    class ServiceClient:
        def __init__(self, *_args): pass
        def invoke(self, operation, payload, context):
            try:
                return s.service.handle(operation, payload, OperationContext.from_platform(context))
            except (ValueError, ApplicationPlatformError) as error:
                raise ApplicationTransportError(str(error)) from error
    monkeypatch.setattr(gateway, "ApplicationServiceClient", ServiceClient)
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(applications=ApplicationRuntimeSettings(
        enabled=True, key_root=s.runtime_socket.parent)))
    install_response_transport(monkeypatch)
    yield s
    for runtime in s.agents.values(): runtime.close()


def invoke(s, operation, payload=None, request_id=None, token=None):
    body = {"payload": payload or {}, "ui_context": s.ui}
    if request_id: body["idempotency_key"] = request_id
    return s.http.post(s.base + "/operator/operations/" + operation, json=body,
        headers={"Authorization": "Bearer " + (token or s.user_token)})


def execute(s, numeric_id=1):
    with Session(s.engine) as db:
        device = db.get(Device, numeric_id)
        command = deliver_next_command(db, device=device)
        assert command is not None
        envelope = command_envelope(command, device.device_id)
        payload = command.payload
        result = s.journals[numeric_id].execute(envelope,
            lambda: s.agents[numeric_id].invoke(payload["capability_id"], payload["action"], payload["arguments"],
                contract_version=payload["contract_version"], contract_digest=payload["contract_digest"]),
            authorize=lambda: authorize_execution(db, device, command.command_id))
        record_command_result(db, device=device, result=result)
        assert result.status == "succeeded"
        return envelope, result


def test_operator_ui_sdk_confirmed_on_off_and_restart_without_replay(button):
    s = button
    observation = invoke(s, "observe")
    assert observation.status_code == 200, observation.text
    assert observation.json()["access"] == "granted"
    for value in (True, False):
        request_id = identity()
        reply = invoke(s, "set_output", {"value": value}, request_id)
        assert reply.status_code == 200, reply.text
        assert reply.json()["status"] == "queued" and reply.json()["confirmed_value"] is None
        # Identical retry is the same command; a changed value is refused.
        assert invoke(s, "set_output", {"value": value}, request_id).json()["command_id"] == reply.json()["command_id"]
        assert invoke(s, "set_output", {"value": not value}, request_id).status_code != 200
        envelope, result = execute(s)
        assert s.drivers[1].output("gpio.output.1").read() is value
        s.server.stop(); s.server.start()
        observed = invoke(s, "lookup", {"request_id": request_id})
        assert observed.status_code == 200, observed.text
        assert observed.json()["status"] == "succeeded" and observed.json()["confirmed_value"] is value
        recovered = s.journals[1].execute(envelope, lambda: pytest.fail("Replayed an existing effect"))
        assert recovered == result
        # Another actor cannot read this actor's request, even knowing its UUID.
        assert invoke(s, "lookup", {"request_id": request_id}, token=s.token).json()["status"] == "not_found"


def test_permission_resource_revocation_and_no_administration(button):
    s = button
    assert s.validated.application_extension.routes[0].administration_actions == ()
    assert s.validated.application_extension.routes[0].administration_reads == ()
    with s.engine.begin() as db:
        db.execute(delete(ApplicationPermissionGrant).where(ApplicationPermissionGrant.user_id == 2))
    assert invoke(s, "set_output", {"value": True}, identity()).status_code == 403
    with Session(s.engine) as db, db.begin():
        assert not db.scalars(select(DeviceCommand)).all()
        db.add(ApplicationPermissionGrant(application_installation_id=1, user_id=2, permission_id="control_output"))
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(), expected_revision=status["grant_record_revision"])
    observed = invoke(s, "observe")
    assert observed.status_code == 200 and observed.json()["access"] == "required"
    assert observed.json()["target_device_id"] is None
    assert invoke(s, "set_output", {"value": True}, identity()).json()["status"] == "not_submitted"
    with s.engine.begin() as db: db.execute(update(UserSession).where(UserSession.id == 2).values(is_active=False))
    assert invoke(s, "observe").status_code in (401, 403)


def test_explicit_second_provider_same_package_and_no_old_request_replay(button, monkeypatch):
    s = button
    request_id = identity()
    assert invoke(s, "set_output", {"value": False}, request_id).status_code == 200
    execute(s)
    second_id, second = add_provider(s)
    s.add_agent(second_id)
    calls = []
    state_root = s.root / "helper-state"; state_root.mkdir(mode=0o700)
    monkeypatch.setattr(helper_fencing, "RELEASE_MUTATION_LOCK", s.root / "release.lock")
    def activate(_self, sha, actor, configuration, lifecycle):
        payload = dict(action="activate_application_extension", sha256=sha, requested_by_user_id=actor,
            configuration=configuration, lifecycle=lifecycle)
        with helper_fencing.application_lifecycle_operation(payload, database=s.engine.url.database,
                state_root=state_root, enforce_permissions=False):
            calls.append(configuration)
            assert configuration == {"OUTPUT_DEVICE_ID": second}
            return {"module_id": s.validated.manifest.module_id, "version": s.validated.manifest.version,
                "sha256": sha, "instance_id": lifecycle["instance_id"], "socket_path": "/run/application.sock"}
    monkeypatch.setattr(UpdateHelperClient, "activate_application_extension", activate)
    plan = rebind.preview(s.manager, 1, actor_token=s.token, request_id=identity(), binding_id="output", device_id=second)
    result = rebind.apply(s.manager, 1, actor_token=s.token, request_id=identity(), preview_id=plan["preview_id"],
        expected_revision=plan["revision"], fingerprint=plan["fingerprint"], approve_change=True)
    assert result["state"] == "completed" and len(calls) == 1
    assert invoke(s, "observe").json()["target_device_id"] == second
    # Old request remains history on its original device. It cannot move.
    old = invoke(s, "lookup", {"request_id": request_id}).json()
    assert old["status"] == "invalidated" and old["target_device_id"] == s.configuration["OUTPUT_DEVICE_ID"]
    assert invoke(s, "set_output", {"value": False}, request_id).status_code != 200
    for value in (True, False):
        fresh = identity()
        assert invoke(s, "set_output", {"value": value}, fresh).json()["status"] == "queued"
        execute(s, second_id)
        assert invoke(s, "lookup", {"request_id": fresh}).json()["confirmed_value"] is value
    assert s.drivers[1].output("gpio.output.1").read() is False
