"""HTTP application for the standalone 3mm Agent."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from agent import __version__
from agent.config import AgentSettings
from agent.core_client import (
    CommandJournal, CorePublisher, DeviceCredentialStore, OutboxStore,
    ReconciliationStore,
)
from agent.hardware import (
    MockDigitalGpioDriver,
    MockIdentifierAdapter,
    create_gpio_driver,
    create_hardware_driver,
)
from agent.modules.gpio import GPIO_ENTRYPOINT, gpio_runtime_handler
from agent.automation_store import AutomationStore
from agent.identity import AgentIdentity, AgentIdentityStore
from agent.inventory import collect_inventory
from agent.module_runtime import AgentModuleRuntime
from agent.role import AgentRoleResolver
from three_mm_protocol import AgentHealth, AgentHello, AgentInventory, AgentRole
from three_mm_provisioning import FileProvisioningStore


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    identity: AgentIdentity
    inventory: AgentInventory
    role: AgentRole
    started_at: datetime
    started_monotonic: float


class MockGpioInputUpdate(BaseModel):
    value: bool


class MockIdentifierScanRequest(BaseModel):
    opaque_identifier: str
    scan_metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


def _runtime(request: Request) -> AgentRuntime:
    return request.app.state.agent_runtime


def create_app(settings: AgentSettings | None = None) -> FastAPI:
    resolved_settings = settings or AgentSettings.from_env()
    hardware = create_hardware_driver(resolved_settings.hardware_profile)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_role = resolved_settings.role
        if resolved_settings.provisioning_data_dir is not None:
            resolved_role = AgentRoleResolver(
                FileProvisioningStore(resolved_settings.provisioning_data_dir)
            ).resolve(resolved_role)
        identity = AgentIdentityStore(resolved_settings.data_dir).load_or_create()
        def current_inventory() -> AgentInventory:
            inventory = collect_inventory(identity.device_id, hardware)
            if resolved_settings.identifier_driver == "mock":
                inventory = inventory.model_copy(
                    update={
                        "capabilities": tuple(
                            dict.fromkeys(
                                (*inventory.capabilities, "identifier.scan.v1")
                            )
                        )
                    }
                )
            return inventory

        app.state.agent_runtime = AgentRuntime(
            identity=identity,
            inventory=current_inventory(),
            role=resolved_role,
            started_at=datetime.now(UTC),
            started_monotonic=time.monotonic(),
        )
        publisher = None
        app.state.module_event_sink = lambda _event: None
        gpio = create_gpio_driver(
            resolved_settings.hardware_profile,
            driver_name=resolved_settings.gpio_driver,
            chip=resolved_settings.gpio_chip,
            inputs=resolved_settings.gpio_inputs,
            outputs=resolved_settings.gpio_outputs,
        )
        app.state.mock_gpio = gpio if isinstance(gpio, MockDigitalGpioDriver) else None
        app.state.mock_identifier = (
            MockIdentifierAdapter(
                resolved_settings.data_dir / "identifier-sequence.json",
                reader_id=resolved_settings.identifier_reader_id,
            )
            if resolved_settings.identifier_driver == "mock"
            else None
        )
        module_runtime = AgentModuleRuntime(
            resolved_settings.data_dir,
            architecture=app.state.agent_runtime.inventory.architecture,
            runtime_handlers={GPIO_ENTRYPOINT: gpio_runtime_handler(gpio, lambda event: app.state.module_event_sink(event))} if gpio else {},
        )
        module_runtime.start_active()
        automation_store = AutomationStore(resolved_settings.data_dir, module_runtime)
        automation_store.activate_all(device_id=identity.device_id)
        if resolved_settings.core_url:
            credential = DeviceCredentialStore(resolved_settings.data_dir).load()
            if credential is not None:
                if credential.device_id != identity.device_id:
                    raise RuntimeError("Core credential does not match Agent identity")
                publisher = CorePublisher(
                    core_url=resolved_settings.core_url,
                    credential=credential,
                    inventory_provider=current_inventory,
                    command_journal=CommandJournal(resolved_settings.data_dir),
                    reconciliation_store=ReconciliationStore(resolved_settings.data_dir),
                    outbox=OutboxStore(resolved_settings.data_dir),
                    module_runtime=module_runtime,
                    automation_store=automation_store,
                    started_monotonic=app.state.agent_runtime.started_monotonic,
                    interval_seconds=resolved_settings.heartbeat_interval_seconds,
                )
                publisher.start()
                app.state.module_event_sink = publisher.publish_event
        yield
        if publisher is not None:
            publisher.stop()
        module_runtime.close()
        gpio.close()

    app = FastAPI(
        title="3mm Agent",
        version=__version__,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["system"])
    def health(request: Request) -> AgentHealth:
        runtime = _runtime(request)
        return AgentHealth(
            agent_version=__version__,
            device_id=runtime.identity.device_id,
            uptime_seconds=time.monotonic() - runtime.started_monotonic,
            checked_at=datetime.now(UTC),
        )

    @app.get("/ready", tags=["system"])
    def readiness(request: Request) -> dict[str, str]:
        runtime = _runtime(request)
        return {"status": "ready", "device_id": runtime.identity.device_id}

    @app.get(
        "/api/v1/agent/hello",
        response_model=AgentHello,
        tags=["agent"],
    )
    def hello(request: Request) -> AgentHello:
        runtime = _runtime(request)
        return AgentHello(
            agent_version=__version__,
            device_id=runtime.identity.device_id,
            display_name=resolved_settings.display_name,
            role=runtime.role,
            started_at=runtime.started_at,
            capabilities=runtime.inventory.capabilities,
        )

    @app.get(
        "/api/v1/agent/inventory",
        response_model=AgentInventory,
        tags=["agent"],
    )
    def inventory(request: Request) -> AgentInventory:
        return _runtime(request).inventory

    @app.get("/api/v1/agent/mock-gpio/state", tags=["diagnostics"])
    def mock_gpio_state(request: Request) -> dict[str, dict[str, bool]]:
        """Return isolated test GPIO state; the Agent service is loopback-only."""
        gpio = request.app.state.mock_gpio
        if gpio is None:
            raise HTTPException(404, "Mock GPIO diagnostics are disabled")
        return {
            "inputs": {"gpio.input.1": gpio.input("gpio.input.1").read()},
            "outputs": {"gpio.output.1": gpio.output("gpio.output.1").read()},
        }

    @app.post("/api/v1/agent/mock-gpio/inputs/{capability_id}", tags=["diagnostics"])
    def set_mock_gpio_input(
        capability_id: str, payload: MockGpioInputUpdate, request: Request
    ) -> dict[str, object]:
        """Simulate a test input transition without exposing any real GPIO."""
        if request.app.state.mock_gpio is None:
            raise HTTPException(404, "Mock GPIO diagnostics are disabled")
        try:
            event = request.app.state.mock_gpio.set_input(capability_id, payload.value)
        except KeyError as exc:
            raise HTTPException(404, "Mock GPIO input was not found") from exc
        return {"changed": event is not None, "sequence": event.sequence if event else None}

    @app.post("/api/v1/agent/mock-identifier/scan", tags=["diagnostics"])
    def emit_mock_identifier_scan(
        payload: MockIdentifierScanRequest,
        request: Request,
    ) -> dict[str, object]:
        """Emit one opaque scan through the normal persistent Agent outbox."""
        adapter = request.app.state.mock_identifier
        if adapter is None:
            raise HTTPException(404, "Mock identifier diagnostics are disabled")
        try:
            event = adapter.scan(
                payload.opaque_identifier,
                metadata=payload.scan_metadata,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        request.app.state.module_event_sink(event)
        return {
            "status": "emitted",
            "sequence": event["payload"]["sequence"],
            "reader_id": event["payload"]["reader_id"],
        }

    return app


app = create_app()
