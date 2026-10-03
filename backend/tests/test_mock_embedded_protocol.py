"""Common Core proof: independent firmware provider + Linux module/application.

No Fleet extension is loaded. In-process HTTP and mock hardware are deliberate;
this is not a live deployment or actual embedded firmware.
"""

import base64
import hashlib
import hmac
import io
import json
import socket
import threading
import time
import zipfile
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import pytest
import requests
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from backend.db.device import (
    Device,
    DeviceCommand,
    DeviceCredential as StoredCredential,
    DeviceEvent,
    DevicePairingRequest,
)
from backend.db.module import (
    ApplicationExtensionInstallation,
    ModuleInstallation,
    ModulePackage,
)
from backend.db.application_command import ApplicationCommandRequest
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
from backend.tests.test_module_packages import (
    application_definition,
    application_manifest,
    application_package,
)
from backend.services.application_platform import ApplicationPlatformServer
from backend.services.device_commands import command_envelope
from backend.services.module_packages import validate_module_package
from backend.utils import jwt_utils
from examples.mock_embedded.client import (
    CAPABILITY,
    CHANNEL,
    PROVIDER,
    MockEmbeddedClient,
    ProtocolRejected,
)
from three_mm_protocol import AgentHeartbeat

ORIGIN = "http://core.test:8887"


class CoreTransport:
    """HTTP adapter plus deterministic faults before/after Core's committed reply."""

    def __init__(self, client):
        self.client = client
        self.offline = False
        self.lose_reply_path = None

    def request(self, method, url, **kwargs):
        assert url.startswith(ORIGIN + "/")
        if self.offline:
            raise requests.ConnectionError("simulated disconnect")
        kwargs.pop("timeout", None)
        kwargs.pop("allow_redirects", None)
        path = urlsplit(url).path
        response = self.client.request(method, path, **kwargs)
        if path == self.lose_reply_path:
            self.lose_reply_path = None
            raise requests.ConnectionError(
                "simulated lost acknowledgement after commit"
            )
        return response


@pytest.fixture
def core(monkeypatch):
    monkeypatch.setattr(jwt_utils, "SECRET_KEY", "c3-test-only-key-at-least-32-bytes")
    monkeypatch.setattr("agent.inventory._network_manager_active", lambda: None)
    monkeypatch.setattr(
        "backend.routes.device_events.process_application_event", lambda *_: None
    )
    client, db, admin, viewer = make_client()
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
    transport = CoreTransport(client)
    yield client, db, {"Authorization": f"Bearer {admin}"}, {
        "Authorization": f"Bearer {viewer}"
    }, transport
    client.close()
    engine = db.get_bind()
    db.close()
    engine.dispose()


def approve(core, node):
    client, db, admin, viewer, _ = core
    assert node.enroll() == "pending_approval"
    request = db.scalar(
        select(DevicePairingRequest).where(
            DevicePairingRequest.requested_device_id == node.device_id
        )
    )
    path = f"/api/v1/pairing/requests/{request.id}/approve"
    assert client.post(path, headers=viewer).status_code == 403
    assert client.post(path, headers=admin).status_code == 200
    assert node.enroll() == "approved"


def invoke(client, admin, prefix):
    response = client.post(
        prefix + "/capabilities/invoke",
        headers=admin,
        json={
            "capability_id": CAPABILITY,
            "action": "set_output",
            "arguments": {"channel": CHANNEL, "value": True},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["command_id"]


def signed_application_acceptance(core, monkeypatch, tmp_path, publisher, gpio, node):
    """Same signed SDK request and declared binding, no provider/platform choice."""
    client, db, admin, _, transport = core
    definition = application_definition(
        command_bindings=[
            {
                "binding_id": "output",
                "target_device_config_key": "OUTPUT_DEVICE_ID",
                "capability_id": CAPABILITY,
                "action": "set_output",
                "arguments_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "channel": {
                            "type": "string",
                            "maxLength": 32,
                            "enum": [CHANNEL],
                        },
                        "value": {"type": "boolean"},
                    },
                    "required": ["channel", "value"],
                },
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
    application = ApplicationExtensionInstallation(
        module_id=package.module_id,
        module_package_id=package.id,
        instance_id="a" * 24,
        active_version=package.version,
        status="active",
        enabled=True,
        socket_path="unused-test-service.sock",
    )
    db.add(application)
    db.commit()
    keys = tmp_path / "keys"
    keys.mkdir()
    secret = b"s" * 32  # Disposable test-only installation transport key.
    assert len(secret) == 32
    (keys / f"{application.instance_id}.key").write_bytes(secret)
    server = ApplicationPlatformServer(tmp_path / "unused-platform.sock", keys)
    engine = db.get_bind()
    monkeypatch.setattr("backend.database.SessionLocal", lambda: Session(engine))

    class Connection:
        # Real signed framing/validation/dispatch, no Windows Unix socket service.
        def __init__(self, message):
            self.message = message

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def recv(self, size):
            return json.dumps(self.message).encode() + b"\n"

        def sendall(self, response):
            self.response = json.loads(response)

    def submit(request_id, signature=True):
        message = {
            "version": 1,
            "instance_id": application.instance_id,
            "timestamp": int(time.time()),
            "request_id": request_id,
            "action": "command.submit",
            "command": {
                "binding_id": "output",
                "request_id": request_id,
                "arguments": {"channel": CHANNEL, "value": False},
                "ttl_seconds": 10,
            },
        }
        message["signature"] = (
            hmac.new(secret, server._canonical(message), hashlib.sha256).hexdigest()
            if signature
            else "invalid"
        )
        connection = Connection(message)
        server._handle(connection)
        response = connection.response
        assert hmac.compare_digest(
            response["signature"],
            hmac.new(secret, server._canonical(response), hashlib.sha256).hexdigest(),
        )
        return response

    before = db.query(DeviceCommand).count()
    assert submit("invalid-signature", signature=False)["ok"] is False
    assert db.query(DeviceCommand).count() == before
    for device_id, execute in (
        (publisher.credential.device_id, publisher._poll_command),
        (node.device_id, node.poll),
    ):
        application.configuration = {"OUTPUT_DEVICE_ID": device_id}
        db.commit()
        request_id = f"c9:{device_id}"
        accepted = submit(request_id)
        assert accepted["ok"] is True, accepted
        command_id = accepted["result"]["command_id"]
        assert submit(request_id)["result"]["command_id"] == command_id
        stored = db.scalar(
            select(DeviceCommand).where(DeviceCommand.command_id == command_id)
        )
        assert stored.command_type == "application.capability.invoke"
        assert (
            "provider_type" not in stored.payload and "module_id" not in stored.payload
        )
        execute()
        node.flush()
        db.refresh(stored)
        assert (
            stored.status == "succeeded"
            and stored.result["execution_state"] == "executed"
        )
        db.expire_all()
        assert db.get(ApplicationCommandRequest, command_id).claimed is True
        state = client.get(
            f"/api/v1/devices/{device_id}/capabilities/{CAPABILITY}/state",
            headers=admin,
        )
        assert state.status_code == 200 and state.json()["values"] == {CHANNEL: False}
        if device_id == node.device_id:
            # Durable receipt can be replayed, never another permit or action.
            executions = node.executions
            assert (
                node.execute(command_envelope(stored, device_id)).status == "succeeded"
            )
            assert node.executions == executions
            assert (
                node._request(
                    "POST", node.prefix + f"/commands/{command_id}/authorize-execution"
                ).status_code
                == 409
            )
            node.flush()
    assert gpio.output(CHANNEL).read() is False and node.output is False

    # Lifecycle invalidation between dispatch and permit must reject the action.
    rejected = submit("c9:disabled-between-dispatch-and-permit")
    assert rejected["ok"] is True
    command = node._body(node._request("GET", node.prefix + "/commands/next"))
    application.enabled = False
    db.commit()
    from three_mm_protocol import AgentCommand

    executions = node.executions
    result = node.execute(AgentCommand.model_validate(command))
    assert (
        result.output["execution_state"] == "not_executed"
        and node.executions == executions
    )
    node.flush()

    # Core consumes a permit, but the acknowledgement is lost. No action/retry.
    application.enabled = True
    db.commit()
    accepted = submit("c9:lost-permit-reply")
    assert accepted["ok"] is True
    command_id = accepted["result"]["command_id"]
    transport.lose_reply_path = (
        node.prefix + f"/commands/{command_id}/authorize-execution"
    )
    result = node.poll()
    assert result.output["execution_state"] == "not_executed"
    assert node.executions == executions
    db.expire_all()
    assert db.get(ApplicationCommandRequest, command_id).claimed is True
    stored = db.scalar(
        select(DeviceCommand).where(DeviceCommand.command_id == command_id)
    )
    assert node.execute(command_envelope(stored, node.device_id)) == result
    assert node.executions == executions
    node.flush()


def test_embedded_full_protocol_lost_replies_disconnect_and_reconnect(core, tmp_path):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    identity = node.identity.copy()
    prefix = node.prefix
    try:
        transport.lose_reply_path = "/api/v1/pairing/enroll"
        with pytest.raises(requests.ConnectionError):
            node.enroll()
        approve(core, node)
        assert db.query(DevicePairingRequest).count() == 1
        assert node.tick() == "approved"
        device = client.get(prefix, headers=admin).json()
        assert device["online"] is True
        inventory = device["latest_inventory"]
        assert (
            inventory["schema_version"] == 2
            and inventory["platform"]["family"] == "embedded"
        )
        assert "kernel_version" not in inventory and "python_version" not in inventory
        caps = client.get(
            prefix + "/capabilities?registry_version=2", headers=admin
        ).json()
        assert caps[0]["capability_id"] == CAPABILITY
        assert caps[0]["provider_type"] == "embedded_firmware"
        assert (
            db.query(ModuleInstallation).count() == db.query(ModulePackage).count() == 0
        )

        command_id = invoke(client, admin, prefix)
        assert node.poll().status == "succeeded"
        transport.offline = True
        with pytest.raises(requests.ConnectionError):
            node.flush()
        assert node.pending_count == 3 and node.executions == 1
        transport.offline = False
        transport.lose_reply_path = prefix + "/events"
        with pytest.raises(requests.ConnectionError):
            node.flush()
        assert (
            db.query(DeviceEvent).filter_by(event_type="gpio.output.changed").count()
            == 1
        )
        assert node.pending_count == 2  # State acked, event/result persisted.
        node.close()
        node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
        assert (
            node.identity == identity and node.output is True and node.executions == 1
        )
        assert node.enroll() == "approved"
        # Advance only the test's delivery lease, then redeliver via real Core GET.
        queued = db.scalar(
            select(DeviceCommand).where(DeviceCommand.command_id == command_id)
        )
        queued.delivered_at = datetime.now(UTC) - timedelta(seconds=31)
        db.commit()
        assert node.poll().status == "succeeded" and node.executions == 1
        node.flush()
        assert node.pending_count == 0
        assert (
            db.query(DeviceEvent).filter_by(event_type="gpio.output.changed").count()
            == 1
        )
        history = client.get(prefix + "/commands", headers=admin).json()["items"]
        assert (
            next(row for row in history if row["command_id"] == command_id)["status"]
            == "succeeded"
        )
        assert client.get(
            prefix + f"/capabilities/{CAPABILITY}/state", headers=admin
        ).json()["values"] == {CHANNEL: True}

        desired = client.put(
            prefix + "/desired-state",
            headers=admin,
            json={"expected_revision": 0, "state": {"threshold": 3}},
        )
        assert desired.status_code == 200
        node.reconcile()
        node.flush()
        assert node._get("desired_state") == {"threshold": 3}
        assert (
            client.get(prefix + "/state", headers=admin).json()["synchronized"] is True
        )
        before = node.register_capability()
        assert node.tick() == "approved"
        assert node.register_capability().revision == before.revision
        assert db.query(Device).count() == db.query(StoredCredential).count() == 1
        # Admin disable is authoritative: the node report cannot re-enable it.
        disabled = client.post(
            prefix + f"/capability-providers/embedded_firmware/{PROVIDER}/enabled",
            headers=admin,
            json={"enabled": False, "expected_revision": before.revision},
        )
        assert disabled.status_code == 200, disabled.text
        assert node.register_capability().enabled is False
        assert (
            client.get(
                prefix + "/capabilities?registry_version=2", headers=admin
            ).json()
            == []
        )
        assert (
            client.post(
                prefix + f"/credentials/{identity['credential_id']}/revoke",
                headers=admin,
            ).status_code
            == 200
        )
        assert node.enroll() == "revoked"
        with pytest.raises(ProtocolRejected) as rejected:
            node.heartbeat()
        assert rejected.value.status_code == 401 and node.identity == identity
    finally:
        node.close()


def test_independent_client_uses_real_http_socket(core, tmp_path):
    """No monkeypatch or injected transport: requests -> loopback -> Core routers."""
    client, db, admin, _, _ = core
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(
        uvicorn.Config(client.app, log_level="critical", lifespan="off")
    )
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [listener]}, daemon=True
    )
    node = MockEmbeddedClient(origin, tmp_path)
    admin_transport = requests.Session()
    admin_transport.trust_env = False
    try:
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        assert server.started
        assert node.tick() == "pending_approval"
        pending = admin_transport.get(
            origin + "/api/v1/pairing/requests", headers=admin, timeout=5
        )
        assert pending.status_code == 200
        request = db.scalar(
            select(DevicePairingRequest).where(
                DevicePairingRequest.requested_device_id == node.device_id
            )
        )
        response = admin_transport.post(
            origin + f"/api/v1/pairing/requests/{request.id}/approve",
            headers=admin,
            timeout=5,
        )
        assert response.status_code == 200
        assert node.tick() == "approved"
        invoked = admin_transport.post(
            origin + node.prefix + "/capabilities/invoke",
            headers=admin,
            json={
                "capability_id": CAPABILITY,
                "action": "set_output",
                "arguments": {"channel": CHANNEL, "value": True},
            },
            timeout=5,
        )
        assert invoked.status_code == 200
        assert (
            node.tick() == "approved" and node.executions == 1 and node.output is True
        )
        history = admin_transport.get(
            origin + node.prefix + "/commands", headers=admin, timeout=5
        ).json()
        assert history["items"][0]["status"] == "succeeded"
        assert db.query(ModulePackage).count() == 0
    finally:
        node.close()
        admin_transport.close()
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
    assert not thread.is_alive()


@pytest.mark.parametrize("role", ["standalone", "hub"])
def test_linux_local_agent_and_embedded_node_share_core_without_fleet(
    core, monkeypatch, tmp_path, role
):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path / "embedded", transport=transport)
    agent_dir = tmp_path / "linux"
    identity = AgentIdentityStore(agent_dir).load_or_create()
    prefix = f"/api/v1/devices/{identity.device_id}"
    hardware = MockHardwareDriver.for_profile(HardwareProfile.MOCK_PI3)
    gpio = MockDigitalGpioDriver()
    runtime = AgentModuleRuntime(
        agent_dir,
        architecture=hardware.collect().architecture,
        runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(gpio, lambda *_: None)},
    )
    monkeypatch.setattr(
        "agent.core_client.requests.get",
        lambda url, **kw: transport.request("GET", url, **kw),
    )
    monkeypatch.setattr(
        "agent.core_client.requests.post",
        lambda url, **kw: transport.request("POST", url, **kw),
    )
    monkeypatch.setattr(
        "agent.core_client.requests.put",
        lambda url, **kw: transport.request("PUT", url, **kw),
    )
    try:
        issued = client.post("/api/v1/pairing-codes", headers=admin).json()
        assert (
            client.post(
                "/api/v1/pairing/claim",
                json={
                    "code": issued["code"],
                    "device_id": identity.device_id,
                    "public_key": "ssh-ed25519 c3-test-public-key",
                    "display_name": "Local Linux",
                    "role": role,
                    "protocol_version": "1.0",
                },
            ).status_code
            == 202
        )
        assert (
            client.post(
                f"/api/v1/pairing/requests/{issued['request_id']}/approve",
                headers=admin,
            ).status_code
            == 200
        )
        credential = DeviceCredential.model_validate(
            client.post(
                "/api/v1/pairing/complete",
                json={"code": issued["code"], "device_id": identity.device_id},
            ).json()
        )
        DeviceCredentialStore(agent_dir).save(credential)
        publisher = CorePublisher(
            core_url=ORIGIN,
            credential=credential,
            inventory_provider=lambda: collect_inventory(identity.device_id, hardware),
            command_journal=CommandJournal(agent_dir),
            reconciliation_store=ReconciliationStore(agent_dir),
            outbox=OutboxStore(agent_dir),
            started_monotonic=time.monotonic(),
            module_runtime=runtime,
            inventory_schema_version=2,
            feature_negotiation=True,
        )
        publisher._publish_inventory()
        publisher._post(
            "heartbeat",
            AgentHeartbeat(
                device_id=identity.device_id,
                sent_at=datetime.now(UTC),
                uptime_seconds=1,
            ).model_dump(mode="json"),
        )
        blob = gpio_package(outputs={CHANNEL: False})
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
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
        install = client.post(
            prefix + "/commands",
            headers=admin,
            json={
                "command_type": "module.install",
                "idempotency_key": "c3-linux-install",
                "payload": {
                    "package_base64": base64.b64encode(blob).decode(),
                    "sha256": package.sha256,
                },
            },
        )
        assert install.status_code == 200
        linux = db.scalar(select(Device).where(Device.device_id == identity.device_id))
        installation = ModuleInstallation(
            device_id=linux.id,
            module_package_id=package.id,
            module_id=package.module_id,
            desired_version=package.version,
            status="queued",
            enabled=True,
            command_id=install.json()["command_id"],
        )
        db.add(installation)
        db.commit()
        publisher._poll_command()
        db.refresh(installation)
        assert installation.status == "succeeded"
        approve(core, node)
        assert node.tick() == "approved"
        for target, provider_type in (
            (prefix, "agent_module"),
            (node.prefix, "embedded_firmware"),
        ):
            caps = client.get(
                target + "/capabilities?registry_version=2", headers=admin
            ).json()
            assert (
                next(item for item in caps if item["capability_id"] == CAPABILITY)[
                    "provider_type"
                ]
                == provider_type
            )
            invoke(client, admin, target)
        publisher._poll_command()
        assert node.poll().status == "succeeded"
        node.flush()
        assert gpio.output(CHANNEL).read() is True and node.output is True
        for target in (prefix, node.prefix):
            state = client.get(
                target + f"/capabilities/{CAPABILITY}/state", headers=admin
            )
            assert state.status_code == 200 and state.json()["values"] == {
                CHANNEL: True
            }
        assert db.query(Device).count() == 2
        assert db.query(ModuleInstallation).count() == 1
        assert db.query(ModulePackage).count() == 1
        assert linux.role == role
        signed_application_acceptance(
            core, monkeypatch, tmp_path, publisher, gpio, node
        )
    finally:
        runtime.close()
        node.close()
