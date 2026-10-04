"""C11: one application contract across Linux/module and firmware providers."""

import hashlib
import io
import json
import time
import zipfile
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from agent.core_client import (
    CorePublisher,
    DeviceCredential,
    CommandJournal,
    ReconciliationStore,
    OutboxStore,
)
from agent.hardware import MockDigitalGpioDriver
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from agent.tests.test_module_runtime import gpio_package
from backend.db.device import (
    Device,
    DeviceCommand,
    DeviceCredential as StoredCredential,
    DeviceRuntimeFeatures,
)
from backend.db.module import (
    ModulePackage,
    ModuleInstallation,
    ApplicationExtensionInstallation,
)
from backend.db.application_command import ApplicationCommandRequest
from backend.services.device_pairing import credential_secret_hash
from backend.services.ai_capability_context import build_automation_capability_context
from backend.services.module_packages import validate_module_package
from backend.services.device_commands import (
    command_envelope,
    deliver_next_command,
    queue_command,
    DeviceCommandError,
)
from backend.services.application_commands import submit_command, authorize_execution
from backend.tests.test_mock_embedded_protocol import (
    core,
    approve,
    ORIGIN,
)  # noqa: F401
from backend.tests.test_module_packages import (
    application_definition,
    application_manifest,
    application_package,
)
from examples.mock_embedded.client import MockEmbeddedClient, CAPABILITY, CHANNEL
from examples.mock_embedded.contracts import control_contract
from three_mm_protocol import AgentCommand
from three_mm_protocol.capability_contracts import (
    CONTRACT_FEATURE,
    CapabilityContractError,
)
from three_mm_protocol.node_security import NODE_MESSAGE_BYTES, validate_command_payload


def versioned_package():
    blob = gpio_package(outputs={CHANNEL: False})
    with zipfile.ZipFile(io.BytesIO(blob)) as source:
        files = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["version"] = "1.0.6"
    for registration in manifest["registrations"]:
        if registration["registration_id"] == CAPABILITY:
            registration["contract"] = control_contract().model_dump(mode="json")
    files["manifest.json"] = json.dumps(manifest).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.fixture
def pair(core, monkeypatch, tmp_path):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(
        ORIGIN, tmp_path / "embedded", transport=transport, contract=control_contract()
    )
    approve(core, node)
    assert node.tick() == "approved"
    device = Device(
        device_id="dev_" + "7" * 32,
        display_name="Local Linux",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
    )
    credential = DeviceCredential(
        device_id=device.device_id,
        credential_id="cred_" + "8" * 32,
        credential_secret="c11-test-only-secret" * 3,
    )
    db.add(device)
    db.flush()
    db.add(
        StoredCredential(
            device_id=device.id,
            credential_id=credential.credential_id,
            secret_hash=credential_secret_hash(credential.credential_secret),
        )
    )
    blob = versioned_package()
    validated = validate_module_package(blob)
    package = ModulePackage(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        manifest=validated.manifest.model_dump(mode="json"),
        registrations=[
            item.model_dump(mode="json") for item in validated.manifest.registrations
        ],
        sha256=validated.sha256,
        size_bytes=len(blob),
        file_path="unused",
    )
    db.add(package)
    db.flush()
    db.add(
        ModuleInstallation(
            device_id=device.id,
            module_package_id=package.id,
            module_id=package.module_id,
            desired_version=package.version,
            status="succeeded",
            enabled=True,
        )
    )
    db.commit()
    gpio = MockDigitalGpioDriver()
    root = tmp_path / "linux"
    runtime = AgentModuleRuntime(
        root,
        architecture="aarch64",
        runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(gpio)},
    )
    runtime.install(blob, expected_sha256=validated.sha256)
    for method in ("get", "post", "put"):
        monkeypatch.setattr(
            "agent.core_client.requests." + method,
            lambda url, _method=method.upper(), **kwargs: transport.request(
                _method, url, **kwargs
            ),
        )
    publisher = CorePublisher(
        core_url=ORIGIN,
        credential=credential,
        inventory_provider=lambda: None,
        command_journal=CommandJournal(root),
        reconciliation_store=ReconciliationStore(root),
        outbox=OutboxStore(root),
        started_monotonic=time.monotonic(),
        module_runtime=runtime,
        feature_negotiation=True,
    )
    publisher._negotiated_inventory_version()
    try:
        yield core, node, device, publisher, runtime, gpio, package
    finally:
        runtime.close()
        node.close()


def application(db, tmp_path, target):
    definition = application_definition(
        command_bindings=[
            {
                "binding_id": "output",
                "target_device_config_key": "OUTPUT_DEVICE_ID",
                "capability_id": CAPABILITY,
                "contract_version": "1.0",
                "action": "set_output",
                "arguments_schema": control_contract()
                .actions["set_output"]
                .arguments_schema,
            }
        ]
    )
    definition["service"]["sdk_version"] = "1.3"
    manifest = application_manifest()
    manifest["permissions"].append("capabilities.invoke")
    manifest["capabilities"]["consumes"].append(CAPABILITY)
    manifest["configuration_schema"]["properties"]["OUTPUT_DEVICE_ID"] = {
        "type": "string"
    }
    blob = application_package(definition=definition, manifest_value=manifest)
    validated = validate_module_package(blob)
    archive = tmp_path / "application.zip"
    archive.write_bytes(blob)
    package = ModulePackage(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        manifest=validated.manifest.model_dump(mode="json"),
        registrations=[],
        sha256=validated.sha256,
        size_bytes=len(blob),
        file_path=str(archive),
    )
    db.add(package)
    db.flush()
    app = ApplicationExtensionInstallation(
        module_id=package.module_id,
        module_package_id=package.id,
        active_version=package.version,
        instance_id="a" * 24,
        status="active",
        enabled=True,
        socket_path="unused",
        configuration={"OUTPUT_DEVICE_ID": target},
    )
    db.add(app)
    db.commit()
    return app


def request(identifier):
    return {
        "binding_id": "output",
        "request_id": identifier,
        "arguments": {"channel": CHANNEL, "value": True},
        "ttl_seconds": 10,
    }


@pytest.mark.parametrize("role", ["standalone", "hub"])
def test_same_application_contract_runs_on_both_providers_and_survives_restart(
    pair, tmp_path, role
):
    core, node, device, publisher, runtime, gpio, package = pair
    client, db, admin, *_ = core
    device.role = role
    db.commit()
    app = application(db, tmp_path, device.device_id)
    versions = []
    for target, execute in (
        (device.device_id, publisher._poll_command),
        (node.device_id, node.poll),
    ):
        app.configuration = {"OUTPUT_DEVICE_ID": target}
        db.commit()
        rows = client.get(
            f"/api/v1/devices/{target}/capabilities?registry_version=2", headers=admin
        ).json()
        registration = next(row for row in rows if row["capability_id"] == CAPABILITY)
        assert registration["contract_version"] == "1.0"
        versions.append(registration["provider_version"])
        submitted = submit_command(db, app, request(target))
        assert (
            submit_command(db, app, request(target))["command_id"]
            == submitted["command_id"]
        )
        command = db.scalar(
            select(DeviceCommand).where(
                DeviceCommand.command_id == submitted["command_id"]
            )
        )
        assert command.payload["contract_digest"] == control_contract().digest()
        assert (
            "provider_type" not in command.payload
            and "module_id" not in command.payload
        )
        execute()
        node.flush()
        db.refresh(command)
        assert (
            command.status == "succeeded"
            and command.result["execution_state"] == "executed"
        )
    assert versions == ["1.0.6", "0.2.0"]
    context = build_automation_capability_context(db)
    assert context.context_version == 2
    entries = [
        entry for entry in context.capabilities if entry.capability_id == CAPABILITY
    ]
    assert len(entries) == 2 and all(
        entry.contract_version == "1.0" for entry in entries
    )
    assert len({entry.contract.digest() for entry in entries}) == 1
    assert gpio.output(CHANNEL).read() is True and node.output is True
    # Reload the active module's immutable manifest, not an in-memory catalog.
    runtime.close()
    runtime.start_active()
    assert runtime._contracts[CAPABILITY].digest() == control_contract().digest()


@pytest.mark.parametrize(
    "change",
    ["version", "missing_version", "action", "argument", "extra", "raw", "runtime"],
)
def test_incompatible_requests_fail_before_queue(pair, change):
    core, node, _, _, _, _, _ = pair
    client, db, admin, viewer, _ = core
    payload = {
        "capability_id": CAPABILITY,
        "contract_version": "1.0",
        "action": "set_output",
        "arguments": {"channel": CHANNEL, "value": True},
    }
    if change == "version":
        payload["contract_version"] = "2.0"
    if change == "missing_version":
        payload.pop("contract_version")
    if change == "action":
        payload["action"] = "unknown"
    if change == "argument":
        payload["arguments"]["value"] = 1
    if change == "extra":
        payload["arguments"]["extra"] = True
    if change == "raw":
        payload["contract_version"] = "2.0"
    if change == "runtime":
        firmware = db.scalar(select(Device).where(Device.device_id == node.device_id))
        features = db.scalar(
            select(DeviceRuntimeFeatures).where(
                DeviceRuntimeFeatures.device_id == firmware.id
            )
        )
        declaration = deepcopy(features.declaration)
        declaration["features"].remove(CONTRACT_FEATURE)
        features.declaration = declaration
        db.commit()
    before = db.query(DeviceCommand).count()
    assert (
        client.post(
            node.prefix + "/capabilities/invoke", headers=viewer, json=payload
        ).status_code
        == 403
    )
    path = node.prefix + ("/commands" if change == "raw" else "/capabilities/invoke")
    if change == "raw":
        payload = {
            "command_type": "capability.invoke",
            "payload": payload,
            "idempotency_key": "bad-raw",
        }
    response = client.post(path, headers=admin, json=payload)
    assert response.status_code == 409, response.text
    assert db.query(DeviceCommand).count() == before and node.executions == 0


@pytest.mark.parametrize("change", ["version", "definition", "withdrawal"])
def test_provider_change_blocks_only_never_dispatched_work(pair, tmp_path, change):
    core, _, device, _, _, _, package = pair
    _, db, *_ = core
    app = application(db, tmp_path, device.device_id)
    submitted = submit_command(db, app, request("before-change"))
    registration = deepcopy(package.registrations)
    control = next(row for row in registration if row["registration_id"] == CAPABILITY)
    if change == "version":
        control["contract"]["contract_version"] = "2.0"
    if change == "definition":
        control["contract"]["actions"]["set_output"]["arguments_schema"]["properties"][
            "value"
        ]["enum"] = [True]
    if change == "withdrawal":
        registration.remove(control)
    package.registrations = registration
    db.commit()
    assert deliver_next_command(db, device=device) is None
    command = db.scalar(
        select(DeviceCommand).where(DeviceCommand.command_id == submitted["command_id"])
    )
    assert command.status == "failed" and command.result == {
        "execution_state": "not_dispatched"
    }
    assert command.delivery_attempts == 0 and command.delivered_at is None


def test_contract_digest_must_fit_final_payload_before_queue(pair):
    core, _, device, _, _, _, _ = pair
    _, db, *_ = core
    payload = {
        "capability_id": CAPABILITY,
        "contract_version": "1.0",
        "action": "set_output",
        "arguments": {"channel": CHANNEL, "value": True},
        "padding": "",
    }
    size = len(json.dumps(payload, separators=(",", ":")).encode())
    payload["padding"] = "x" * (NODE_MESSAGE_BYTES - size - 1)
    validate_command_payload("capability.invoke", payload)
    before = db.query(DeviceCommand).count()
    with pytest.raises(DeviceCommandError, match="byte limit"):
        queue_command(
            db,
            device=device,
            command_type="capability.invoke",
            payload=payload,
            idempotency_key="oversized-contract-command",
            ttl_seconds=10,
        )
    assert db.query(DeviceCommand).count() == before


def test_withdrawal_after_delivery_denies_permit_without_rewriting_uncertainty(
    pair, tmp_path
):
    core, _, device, _, _, _, package = pair
    _, db, *_ = core
    app = application(db, tmp_path, device.device_id)
    submitted = submit_command(db, app, request("delivered"))
    command = deliver_next_command(db, device=device)
    when = command.delivered_at
    package.registrations = []
    db.commit()
    with pytest.raises(ValueError):
        authorize_execution(db, device, command.command_id)
    db.rollback()
    db.refresh(command)
    assert command.status == "delivered" and command.delivered_at == when
    assert db.get(ApplicationCommandRequest, submitted["command_id"]).claimed is False


def test_node_checks_live_contract_before_driver_and_preserves_receipt(pair, tmp_path):
    core, node, device, publisher, runtime, gpio, _ = pair
    _, db, *_ = core
    app = application(db, tmp_path, device.device_id)
    submit_command(db, app, request("valid"))
    command = deliver_next_command(db, device=device)
    envelope = command_envelope(command, device.device_id)
    payload = {**envelope.payload, "contract_version": "2.0"}
    with pytest.raises(CapabilityContractError):
        runtime.validate_invocation(payload)
    assert gpio.output(CHANNEL).read() is False
    # Actual publisher + durable physical journal, no runtime exception counted
    # as an attempted hardware effect. Use a different immutable request ID.
    from agent.physical_command_journal import (
        PhysicalCommandJournal,
        PhysicalCommandFailure,
    )

    journal = PhysicalCommandJournal(tmp_path / "bad-command")
    bad = envelope.model_copy(update={"payload": payload})

    def invoke():
        try:
            runtime.validate_invocation(payload)
        except CapabilityContractError as exc:
            raise PhysicalCommandFailure("not_executed", str(exc)) from exc
        return runtime.invoke(
            CAPABILITY, "set_output", payload["arguments"], contract_version="2.0"
        )

    result = journal.execute(bad, invoke)
    assert result.output["execution_state"] == "not_executed"
    assert journal.execute(bad, lambda: pytest.fail("must not replay")) == result
    assert gpio.output(CHANNEL).read() is False
    mock_bad = envelope.model_copy(
        update={
            "device_id": node.device_id,
            "command_id": "cmd_" + uuid4().hex,
            "command_type": "capability.invoke",
            "payload": payload,
        }
    )
    assert (
        node.execute(mock_bad).output["execution_state"] == "not_executed"
        and node.executions == 0
    )
