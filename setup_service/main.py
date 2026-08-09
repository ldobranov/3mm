"""FastAPI application for first-boot browser provisioning."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from setup_service import __version__
from setup_service.config import SetupSettings
from setup_service.schemas import SetupConfiguration, SetupOutcome, SetupStatus
from three_mm_provisioning import (
    FileProvisioningStore,
    NetworkAdapter,
    NetworkCredentials,
    ProvisioningRequest,
    ProvisioningSnapshot,
    ProvisioningState,
    ProvisioningStateMachine,
    ProvisioningStore,
    ProvisioningStoreError,
)
from three_mm_provisioning.mock_network import MockNetworkAdapter

SETUP_PAGE = Path(__file__).with_name("static") / "setup.html"

PUBLIC_SETUP_ENDPOINTS = frozenset(
    {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/ready"),
        ("GET", "/setup"),
        ("GET", "/api/v1/setup/status"),
        ("POST", "/api/v1/setup/configure"),
        ("GET", "/generate_204"),
        ("GET", "/hotspot-detect.html"),
        ("GET", "/connecttest.txt"),
        ("GET", "/ncsi.txt"),
    }
)


@dataclass(frozen=True, slots=True)
class SetupRuntime:
    machine: ProvisioningStateMachine
    store: ProvisioningStore
    lock: Lock


def _runtime(request: Request) -> SetupRuntime:
    return request.app.state.setup_runtime


def create_app(
    network: NetworkAdapter | None = None,
    store: ProvisioningStore | None = None,
    settings: SetupSettings | None = None,
) -> FastAPI:
    resolved_settings = settings or SetupSettings.from_env()
    resolved_network = network or MockNetworkAdapter()
    resolved_store = store or FileProvisioningStore(resolved_settings.data_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        machine = ProvisioningStateMachine(resolved_network)
        snapshot = resolved_store.load()
        if snapshot is None:
            machine.start_setup()
        elif snapshot.state is ProvisioningState.PROVISIONED:
            if snapshot.role is None:
                raise ProvisioningStoreError(
                    "Provisioned snapshot does not contain a role"
                )
            machine.restore_provisioned(snapshot.role)
        else:
            machine.recover_setup()
            resolved_store.clear()
        app.state.setup_runtime = SetupRuntime(
            machine=machine,
            store=resolved_store,
            lock=Lock(),
        )
        yield

    app = FastAPI(
        title="3mm Setup",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def sanitized_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        safe_errors = [
            {
                "type": item["type"],
                "loc": item["loc"],
                "msg": item["msg"],
            }
            for item in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/setup", status_code=307)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    def ready(request: Request) -> dict[str, str]:
        runtime = _runtime(request)
        if runtime.machine.state is ProvisioningState.UNPROVISIONED:
            raise HTTPException(status_code=503, detail="setup_not_ready")
        return {"status": "ready"}

    @app.get("/setup", response_class=HTMLResponse, include_in_schema=False)
    def setup_page() -> HTMLResponse:
        return HTMLResponse(SETUP_PAGE.read_text(encoding="utf-8"))

    @app.get(
        "/api/v1/setup/status",
        response_model=SetupStatus,
        include_in_schema=False,
    )
    def status(request: Request) -> SetupStatus:
        runtime = _runtime(request)
        return SetupStatus(
            state=runtime.machine.state,
            setup_active=runtime.machine.state is ProvisioningState.SETUP,
            role=runtime.machine.role,
        )

    @app.post(
        "/api/v1/setup/configure",
        response_model=SetupOutcome,
        include_in_schema=False,
    )
    def configure(
        configuration: SetupConfiguration,
        request: Request,
    ) -> SetupOutcome:
        runtime = _runtime(request)
        provisioning_request = ProvisioningRequest(
            network=NetworkCredentials(
                network_name=configuration.network_name,
                passphrase=configuration.passphrase.get_secret_value(),
            ),
            locale=configuration.locale,
            device_name=configuration.device_name,
            administrator_name=configuration.administrator_name,
            role=configuration.role,
            hub_endpoint=(
                str(configuration.hub_endpoint)
                if configuration.hub_endpoint is not None
                else None
            ),
        )
        with runtime.lock:
            if runtime.machine.state is not ProvisioningState.SETUP:
                raise HTTPException(
                    status_code=409,
                    detail="setup_not_available",
                )
            try:
                runtime.store.save(ProvisioningSnapshot.attempt_started())
            except ProvisioningStoreError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="setup_persistence_failed",
                ) from exc
            try:
                result = runtime.machine.provision(provisioning_request)
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="setup_not_available",
                ) from exc
            if result.recovery_required:
                try:
                    runtime.store.clear()
                except ProvisioningStoreError as exc:
                    raise HTTPException(
                        status_code=503,
                        detail="setup_persistence_failed",
                    ) from exc
            else:
                try:
                    runtime.store.save(
                        ProvisioningSnapshot.provisioned(provisioning_request)
                    )
                except ProvisioningStoreError as exc:
                    runtime.machine.recover_setup()
                    try:
                        runtime.store.clear()
                    except ProvisioningStoreError:
                        pass
                    raise HTTPException(
                        status_code=503,
                        detail="setup_persistence_failed",
                    ) from exc
        return SetupOutcome(
            state=result.state,
            role=result.role,
            recovery_required=result.recovery_required,
            error_code=result.error_code,
        )

    def captive_portal_redirect() -> RedirectResponse:
        return RedirectResponse("/setup", status_code=307)

    for probe_path in (
        "/generate_204",
        "/hotspot-detect.html",
        "/connecttest.txt",
        "/ncsi.txt",
    ):
        app.add_api_route(
            probe_path,
            captive_portal_redirect,
            methods=["GET"],
            include_in_schema=False,
        )

    return app


app = create_app()
