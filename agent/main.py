"""HTTP application for the standalone 3mm Agent."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI, Request

from agent import __version__
from agent.config import AgentSettings
from agent.core_client import (
    CommandJournal, CorePublisher, DeviceCredentialStore, OutboxStore,
    ReconciliationStore,
)
from agent.hardware import create_hardware_driver
from agent.identity import AgentIdentity, AgentIdentityStore
from agent.inventory import collect_inventory
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
                    started_monotonic=app.state.agent_runtime.started_monotonic,
                    interval_seconds=resolved_settings.heartbeat_interval_seconds,
                )
                publisher.start()
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

    return app


app = create_app()
