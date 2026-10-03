"""C0: joined Linux Agent/Core behavior before inventory/provider refactors.

Actual HTTP routers, credentials, publisher, module runtime and journals;
in-process transport and deterministic hardware, never a live Pi.
"""

import base64
import hashlib
import io
import json
import time
import zipfile
from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
import requests
from sqlalchemy import select

from agent.core_client import (
    CommandJournal,
    CorePublisher,
    DeviceCredential,
    DeviceCredentialStore,
    OutboxStore,
    ReconciliationStore,
)
from agent.hardware import HardwareProfile, MockDigitalGpioDriver, MockHardwareDriver
from agent.identity import AgentIdentityStore
from agent.inventory import collect_inventory
from agent.module_runtime import AgentModuleRuntime
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from agent.tests.test_module_runtime import gpio_package
from backend.db.device import Device, DeviceEvent
from backend.db.module import ModuleInstallation, ModulePackage
from backend.routes import (
    device_capabilities,
    device_capability_state,
    device_commands,
    device_events,
    device_ingest,
    device_registry,
    device_runtime_features,
    device_state,
)
from backend.tests.test_device_pairing_routes import make_client
from backend.utils import jwt_utils
from three_mm_protocol import AgentHeartbeat
from three_mm_protocol.device_inventory import inventory_value


@pytest.mark.parametrize(
    "profile", [HardwareProfile.MOCK_PI3, HardwareProfile.MOCK_LINUX]
)
@pytest.mark.parametrize("inventory_schema_version", [1, 2])
@pytest.mark.parametrize("role", ["standalone", "hub", "node"])
def test_linux_node_protocol_survives_module_install_and_reconnect(
    monkeypatch, tmp_path, profile, inventory_schema_version, role
):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "c0-test-only-key-at-least-32-bytes")
    monkeypatch.setattr("agent.inventory._network_manager_active", lambda: None)
    # Business-extension delivery is tested separately, not part of C0.
    monkeypatch.setattr(
        "backend.routes.device_events.process_application_event", lambda *_args: None
    )
    client, db, admin_token, _ = make_client()
    engine = db.get_bind()
    for module in (
        device_ingest,
        device_registry,
        device_runtime_features,
        device_commands,
        device_capabilities,
        device_capability_state,
        device_events,
        device_state,
    ):
        client.app.include_router(module.router)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    agent_dir = tmp_path / "agent"
    identity = AgentIdentityStore(agent_dir).load_or_create()
    device_id = identity.device_id
    prefix = f"/api/v1/devices/{device_id}"
    events = []
    gpio = MockDigitalGpioDriver()
    hardware = MockHardwareDriver.for_profile(profile)
    runtime = AgentModuleRuntime(
        agent_dir,
        architecture=hardware.collect().architecture,
        runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(gpio, events.append)},
    )
    connected = True

    def transport(method, url, **kwargs):
        if not connected:
            raise requests.ConnectionError("C0 simulated disconnection")
        kwargs.pop("timeout", None)
        kwargs.pop("allow_redirects", None)
        return client.request(method, urlsplit(url).path, **kwargs)

    monkeypatch.setattr(
        "agent.core_client.requests.get", lambda url, **kw: transport("GET", url, **kw)
    )
    monkeypatch.setattr(
        "agent.core_client.requests.post",
        lambda url, **kw: transport("POST", url, **kw),
    )
    monkeypatch.setattr(
        "agent.core_client.requests.put", lambda url, **kw: transport("PUT", url, **kw)
    )

    try:
        issued = client.post("/api/v1/pairing-codes", headers=admin_headers)
        assert issued.status_code == 201
        code = issued.json()
        claim = client.post(
            "/api/v1/pairing/claim",
            json={
                "code": code["code"],
                "device_id": device_id,
                "public_key": "ssh-ed25519 test-only-c0-agent-public-key",
                "display_name": f"C0 Linux {role}",
                "role": role,
                "protocol_version": "1.0",
            },
        )
        assert claim.status_code == 202
        assert db.scalar(select(Device)) is None
        completion = {"code": code["code"], "device_id": device_id}
        assert (
            client.post("/api/v1/pairing/complete", json=completion).status_code == 409
        )
        assert (
            client.post(
                f"/api/v1/pairing/requests/{code['request_id']}/approve",
                headers=admin_headers,
            ).status_code
            == 200
        )
        completed = client.post("/api/v1/pairing/complete", json=completion)
        assert completed.status_code == 200
        credential = DeviceCredential.model_validate(completed.json())
        DeviceCredentialStore(agent_dir).save(credential)

        def publisher():
            return CorePublisher(
                core_url="http://c0-core.test",
                credential=DeviceCredentialStore(agent_dir).load(),
                inventory_provider=lambda: collect_inventory(device_id, hardware),
                command_journal=CommandJournal(agent_dir),
                reconciliation_store=ReconciliationStore(agent_dir),
                outbox=OutboxStore(agent_dir),
                started_monotonic=time.monotonic(),
                module_runtime=runtime,
                inventory_schema_version=inventory_schema_version,
                feature_negotiation=True,
            )

        node = publisher()
        node._publish_inventory()
        node._post(
            "heartbeat",
            AgentHeartbeat(
                device_id=device_id,
                sent_at=datetime.now(UTC),
                uptime_seconds=1,
            ).model_dump(mode="json"),
        )
        registered = client.get(prefix, headers=admin_headers)
        assert registered.status_code == 200
        assert registered.json()["online"] is True
        assert (
            inventory_value(registered.json()["latest_inventory"], "architecture")
            == hardware.collect().architecture
        )

        # Use the real module command/result path, not a fake active installation.
        blob = gpio_package(outputs={"gpio.output.1": False})
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        manifest["compatibility"]["architectures"] = [hardware.collect().architecture]
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("health/ready", "ok")
        blob = output.getvalue()
        package = ModulePackage(
            module_id=manifest["module_id"],
            version=manifest["version"],
            manifest=manifest,
            registrations=manifest["registrations"],
            sha256=hashlib.sha256(blob).hexdigest(),
            size_bytes=len(blob),
            file_path="unused",
        )
        db.add(package)
        db.commit()
        command = client.post(
            f"{prefix}/commands",
            headers=admin_headers,
            json={
                "command_type": "module.install",
                "idempotency_key": "c0-install",
                "payload": {
                    "package_base64": base64.b64encode(blob).decode(),
                    "sha256": package.sha256,
                },
            },
        )
        assert command.status_code == 200
        device = db.scalar(select(Device).where(Device.device_id == device_id))
        assert device.role == role
        installation = ModuleInstallation(
            device_id=device.id,
            module_package_id=package.id,
            module_id=package.module_id,
            desired_version=package.version,
            status="queued",
            enabled=True,
            command_id=command.json()["command_id"],
        )
        db.add(installation)
        db.commit()
        assert client.get(f"{prefix}/capabilities", headers=admin_headers).json() == []
        node._poll_command()
        db.refresh(installation)
        assert installation.status == "succeeded"
        assert installation.installed_version == package.version
        capabilities = client.get(
            f"{prefix}/capabilities", headers=admin_headers
        ).json()
        assert {item["capability_id"] for item in capabilities} == {
            "gpio.digital.input",
            "gpio.digital.control",
        }

        invoked = client.post(
            f"{prefix}/capabilities/invoke",
            headers=admin_headers,
            json={
                "capability_id": "gpio.digital.control",
                "action": "set_output",
                "arguments": {"capability_id": "gpio.output.1", "value": True},
            },
        )
        assert invoked.status_code == 200
        node._poll_command()
        assert gpio.output("gpio.output.1").read() is True
        history = client.get(f"{prefix}/commands", headers=admin_headers).json()[
            "items"
        ]
        result = next(
            item
            for item in history
            if item["command_id"] == invoked.json()["command_id"]
        )
        assert result["status"] == "succeeded"
        assert result["result"]["execution_state"] == "executed"
        state = client.get(
            f"{prefix}/capabilities/gpio.digital.control/state", headers=admin_headers
        )
        assert state.status_code == 200
        assert state.json()["values"] == {"gpio.output.1": True}

        desired = client.put(
            f"{prefix}/desired-state",
            headers=admin_headers,
            json={
                "expected_revision": 0,
                "state": {"inventory_generation": 1},
            },
        )
        assert desired.status_code == 200
        node._reconcile_state()
        assert (
            client.get(f"{prefix}/state", headers=admin_headers).json()["synchronized"]
            is True
        )

        gpio.set_input("gpio.input.1", True)
        node.publish_event(
            next(
                event for event in events if event["event_type"] == "gpio.input.changed"
            )
        )
        event = node._event_queue.get_nowait()
        connected = False
        node._deliver_event(event)
        assert node.outbox.load()
        runtime.close()

        # Reload durable identity/credential/module state, then replay buffered data.
        assert AgentIdentityStore(agent_dir).load_or_create() == identity
        assert DeviceCredentialStore(agent_dir).load() == credential
        runtime.start_active()
        resumed = publisher()
        assert (
            resumed.reconciliation_store.load().applied_revision
            == desired.json()["revision"]
        )
        connected = True
        resumed._flush_outbox()
        assert resumed.outbox.load() == []
        resumed._post("events", event)
        assert db.query(DeviceEvent).filter_by(event_id=event["event_id"]).count() == 1
        assert (
            client.get(f"{prefix}/capabilities", headers=admin_headers).json()
            == capabilities
        )
        assert db.query(Device).count() == 1

        revoke = f"{prefix}/credentials/{credential.credential_id}/revoke"
        assert client.post(revoke, headers=admin_headers).status_code == 200
        assert (
            client.post(
                f"{prefix}/heartbeat",
                headers=resumed.headers,
                json=AgentHeartbeat(
                    device_id=device_id,
                    sent_at=datetime.now(UTC),
                    uptime_seconds=2,
                ).model_dump(mode="json"),
            ).status_code
            == 401
        )
    finally:
        runtime.close()
        client.close()
        db.close()
        engine.dispose()
