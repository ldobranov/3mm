"""FastAPI application for first-boot browser provisioning."""

from __future__ import annotations

import re
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from setup_service import __version__
from setup_service.config import SetupSettings
from setup_service.schemas import (
    SetupConfiguration,
    SetupOutcome,
    SetupPrefill,
    SetupStatus,
    SetupTheme,
    WifiNetworkList,
    WifiNetworkOption,
)
from three_mm_provisioning import (
    FileNetworkRecoveryMarker,
    FileProvisioningStore,
    NetworkAdapter,
    NetworkCredentials,
    NetworkRecoveryStoreError,
    ProvisioningRequest,
    ProvisioningSnapshot,
    ProvisioningState,
    ProvisioningStateMachine,
    ProvisioningStore,
    ProvisioningStoreError,
)
from three_mm_provisioning.mock_network import MockNetworkAdapter
from three_mm_provisioning.network_helper_client import (
    NetworkHelperClientAdapter,
)
from three_mm_provisioning.wifi_scan_cache import (
    merge_wifi_networks,
    read_wifi_scan_cache,
)

SETUP_PAGE = Path(__file__).with_name("static") / "setup.html"

PUBLIC_SETUP_ENDPOINTS = frozenset(
    {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/ready"),
        ("GET", "/setup"),
        ("GET", "/api/v1/setup/status"),
        ("GET", "/api/v1/setup/prefill"),
        ("GET", "/api/v1/setup/networks"),
        ("GET", "/api/v1/setup/theme"),
        ("POST", "/api/v1/setup/configure"),
        ("GET", "/generate_204"),
        ("GET", "/hotspot-detect.html"),
        ("GET", "/connecttest.txt"),
        ("GET", "/ncsi.txt"),
    }
)

THEME_DEFAULTS = {
    "light_body_bg": "#ffffff",
    "light_card_bg": "#ffffff",
    "light_panel_bg": "#f8fafc",
    "light_text_primary": "#222222",
    "light_text_secondary": "#666666",
    "light_card_border": "#d1d5db",
    "light_button_primary_bg": "#007bff",
    "light_border_radius_md": "8",
    "dark_body_bg": "#1f2937",
    "dark_card_bg": "#374151",
    "dark_panel_bg": "#263449",
    "dark_text_primary": "#e5e7eb",
    "dark_text_secondary": "#9ca3af",
    "dark_card_border": "#4b5563",
    "dark_button_primary_bg": "#3b82f6",
    "dark_border_radius_md": "8",
    "header_bg_color": "#4caf50",
    "header_text_color": "#ffffff",
}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _read_setup_theme(database_path: Path) -> SetupTheme:
    values = dict(THEME_DEFAULTS)
    mode = "light"
    try:
        with sqlite3.connect(
            f"file:{database_path.as_posix()}?mode=ro",
            uri=True,
            timeout=1,
        ) as connection:
            rows = connection.execute(
                "SELECT key, value FROM settings "
                "WHERE key IN ("
                "'default_theme','user_theme','header_bg_color','header_text_color',"
                "'light_body_bg','light_card_bg','light_panel_bg',"
                "'light_text_primary','light_text_secondary','light_card_border',"
                "'light_button_primary_bg','light_border_radius_md',"
                "'dark_body_bg','dark_card_bg','dark_panel_bg',"
                "'dark_text_primary','dark_text_secondary','dark_card_border',"
                "'dark_button_primary_bg','dark_border_radius_md'"
                ") ORDER BY id"
            ).fetchall()
        stored = {key: value for key, value in rows if isinstance(value, str)}
        requested_mode = stored.get("user_theme") or stored.get("default_theme")
        if requested_mode in {"light", "dark"}:
            mode = requested_mode
        for key in values:
            candidate = stored.get(key)
            if key.endswith("border_radius_md"):
                if candidate and candidate.isdigit() and 0 <= int(candidate) <= 50:
                    values[key] = candidate
            elif candidate and HEX_COLOR.fullmatch(candidate):
                values[key] = candidate
    except (OSError, sqlite3.Error):
        pass
    prefix = f"{mode}_"
    return SetupTheme(
        mode=mode,
        body_bg=values[f"{prefix}body_bg"],
        card_bg=values[f"{prefix}card_bg"],
        panel_bg=values[f"{prefix}panel_bg"],
        text_primary=values[f"{prefix}text_primary"],
        text_secondary=values[f"{prefix}text_secondary"],
        border=values[f"{prefix}card_border"],
        primary=values[f"{prefix}button_primary_bg"],
        header_bg=values["header_bg_color"],
        header_text=values["header_text_color"],
        border_radius=int(values[f"{prefix}border_radius_md"]),
    )


@dataclass(frozen=True, slots=True)
class SetupRuntime:
    machine: ProvisioningStateMachine
    store: ProvisioningStore
    recovery_marker: FileNetworkRecoveryMarker
    previous_snapshot: ProvisioningSnapshot | None
    lock: Lock


def _runtime(request: Request) -> SetupRuntime:
    return request.app.state.setup_runtime


def create_app(
    network: NetworkAdapter | None = None,
    store: ProvisioningStore | None = None,
    settings: SetupSettings | None = None,
    recovery_marker: FileNetworkRecoveryMarker | None = None,
) -> FastAPI:
    resolved_settings = settings or SetupSettings.from_env()
    resolved_network = network or (
        NetworkHelperClientAdapter(resolved_settings.network_helper_socket)
        if resolved_settings.network_helper_socket is not None
        else MockNetworkAdapter()
    )
    resolved_store = store or FileProvisioningStore(resolved_settings.data_dir)
    resolved_recovery_marker = recovery_marker or FileNetworkRecoveryMarker(
        resolved_settings.data_dir / "network-recovery.json"
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        machine = ProvisioningStateMachine(resolved_network)
        snapshot = resolved_store.load()
        previous_snapshot = None
        if snapshot is None:
            machine.start_setup()
        elif snapshot.state is ProvisioningState.PROVISIONED:
            if snapshot.role is None:
                raise ProvisioningStoreError(
                    "Provisioned snapshot does not contain a role"
                )
            if resolved_recovery_marker.is_active():
                previous_snapshot = snapshot
                machine.recover_setup()
            else:
                machine.restore_provisioned(snapshot.role)
        else:
            machine.recover_setup()
            resolved_store.clear()
        app.state.setup_runtime = SetupRuntime(
            machine=machine,
            store=resolved_store,
            recovery_marker=resolved_recovery_marker,
            previous_snapshot=previous_snapshot,
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

    @app.get(
        "/api/v1/setup/prefill",
        response_model=SetupPrefill,
        include_in_schema=False,
    )
    def prefill(request: Request) -> SetupPrefill:
        snapshot = _runtime(request).previous_snapshot
        if snapshot is None:
            return SetupPrefill()
        return SetupPrefill(
            locale=snapshot.locale,
            device_name=snapshot.device_name,
            administrator_name=snapshot.administrator_name,
            role=snapshot.role,
            hub_endpoint=snapshot.hub_endpoint,
        )

    @app.get(
        "/api/v1/setup/networks",
        response_model=WifiNetworkList,
        include_in_schema=False,
    )
    def networks() -> WifiNetworkList:
        cached_items = read_wifi_scan_cache(resolved_settings.data_dir)
        scanner = getattr(resolved_network, "scan_wifi_networks", None)
        if scanner is None:
            items = cached_items
        else:
            try:
                items = merge_wifi_networks(cached_items, scanner())
            except Exception as exc:
                if not cached_items:
                    raise HTTPException(
                        status_code=503, detail="wifi_scan_failed"
                    ) from exc
                items = cached_items
        return WifiNetworkList(
            items=[
                WifiNetworkOption(
                    network_name=item.network_name,
                    signal=item.signal,
                    secured=item.secured,
                )
                for item in items
            ]
        )

    @app.get(
        "/api/v1/setup/theme",
        response_model=SetupTheme,
        include_in_schema=False,
    )
    def theme() -> SetupTheme:
        return _read_setup_theme(resolved_settings.core_database_path)

    @app.post(
        "/api/v1/setup/configure",
        response_model=SetupOutcome,
        include_in_schema=False,
    )
    def configure(
        configuration: SetupConfiguration,
        request: Request,
        background_tasks: BackgroundTasks,
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
            if runtime.previous_snapshot is None:
                try:
                    runtime.store.save(ProvisioningSnapshot.attempt_started())
                except (ProvisioningStoreError, NetworkRecoveryStoreError) as exc:
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
                if runtime.previous_snapshot is None:
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
                    runtime.recovery_marker.clear()
                except (ProvisioningStoreError, NetworkRecoveryStoreError) as exc:
                    runtime.machine.recover_setup()
                    if runtime.previous_snapshot is None:
                        try:
                            runtime.store.clear()
                        except ProvisioningStoreError:
                            pass
                    raise HTTPException(
                        status_code=503,
                        detail="setup_persistence_failed",
                    ) from exc
                if isinstance(resolved_network, NetworkHelperClientAdapter):
                    background_tasks.add_task(resolved_network.activate_runtime)
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
