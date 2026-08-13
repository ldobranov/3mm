"""HTTP application for the standalone 3mm Agent."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from agent import __version__
from agent.config import AgentSettings
from agent.core_client import (
    CommandJournal, CorePublisher, DeviceCredentialStore, OutboxStore,
    ReconciliationStore,
)
from agent.hardware import create_hardware_driver, create_mock_gpio_driver
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
        app.state.agent_runtime = AgentRuntime(
            identity=identity,
            inventory=collect_inventory(identity.device_id, hardware),
            role=resolved_role,
            started_at=datetime.now(UTC),
            started_monotonic=time.monotonic(),
        )
        publisher = None
        app.state.module_event_sink = lambda _event: None
        gpio = create_mock_gpio_driver(resolved_settings.hardware_profile)
        app.state.mock_gpio = gpio
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
                    inventory_provider=lambda: collect_inventory(identity.device_id, hardware),
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
        return {
            "inputs": {"gpio.input.1": gpio.input("gpio.input.1").read()},
            "outputs": {"gpio.output.1": gpio.output("gpio.output.1").read()},
        }

    @app.post("/api/v1/agent/mock-gpio/inputs/{capability_id}", tags=["diagnostics"])
    def set_mock_gpio_input(
        capability_id: str, payload: MockGpioInputUpdate, request: Request
    ) -> dict[str, object]:
        """Simulate a test input transition without exposing any real GPIO."""
        try:
            event = request.app.state.mock_gpio.set_input(capability_id, payload.value)
        except KeyError as exc:
            raise HTTPException(404, "Mock GPIO input was not found") from exc
        return {"changed": event is not None, "sequence": event.sequence if event else None}

    return app


app = create_app()
