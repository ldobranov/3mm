"""FastAPI application for first-boot browser provisioning."""

from __future__ import annotations

import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from setup_service import __version__
from three_mm_runtime.install_profile import InstallProfile, read_install_profile, validate_profile_role
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
    NetworkRecoveryStoreError,
    ProvisioningState,
    ProvisioningStoreError,
)
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
        ("POST", "/api/v1/setup/finish"),
        ("GET", "/api/v1/setup/capabilities"),
        ("GET", "/api/v1/setup/diagnostics"),
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


def create_app(network=None, store=None, settings=None, recovery_marker=None, *, capability_provider=None):
    from fastapi.responses import Response
    from setup_service.provision import SetupCoordinator, SetupFailure
    from three_mm_provisioning.host_network import HostNetworkAdapter
    from three_mm_provisioning.network import NetworkAdapterError

    resolved_settings = settings or SetupSettings.from_env()
    install_profile = read_install_profile(Path(__file__).resolve().parents[1])
    network = network or (NetworkHelperClientAdapter(resolved_settings.network_helper_socket)
                          if resolved_settings.network_helper_socket else HostNetworkAdapter())
    store = store or FileProvisioningStore(resolved_settings.data_dir)
    marker = recovery_marker or FileNetworkRecoveryMarker(resolved_settings.data_dir / "network-recovery.json")

    def capabilities():
        if resolved_settings.read_only:
            return []
        if capability_provider:
            return capability_provider()
        if isinstance(network, NetworkHelperClientAdapter):
            try:
                result = network._request({"action": "capabilities"})
                return result["interfaces"] if result.get("ok") is True else []
            except Exception:
                return []
        return []

    @asynccontextmanager
    async def lifespan(app):
        app.state.setup_runtime = SetupCoordinator(network, store, marker, resolved_settings, __version__)
        yield

    app = FastAPI(title="3mm Setup", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def protect_setup(request, call_next):
        protected = request.url.path.startswith("/api/v1/setup/") and request.url.path not in {
            "/api/v1/setup/status", "/api/v1/setup/theme"}
        if resolved_settings.read_only and request.method == "POST":
            response = JSONResponse(status_code=403, content={"detail": "local_setup_read_only"})
        elif protected:
            runtime = request.app.state.setup_runtime
            try:
                available = runtime.available
            except (OSError, ValueError, ProvisioningStoreError, NetworkRecoveryStoreError):
                available = False
            if not available:
                response = JSONResponse(status_code=403, content={"detail": "setup_not_available"})
            elif request.method == "POST" and (
                request.headers.get("sec-fetch-site") == "cross-site"
                or request.headers.get("origin", str(request.base_url).rstrip("/")) != str(request.base_url).rstrip("/")
            ):
                response = JSONResponse(status_code=403, content={"detail": "setup_origin_denied"})
            elif request.method == "POST" and request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                response = JSONResponse(status_code=415, content={"detail": "setup_json_required"})
            else:
                if request.method == "POST":
                    chunks = []
                    size = 0
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > 16384:
                            response = JSONResponse(status_code=413, content={"detail": "setup_request_too_large"})
                            break
                        chunks.append(chunk)
                    else:
                        request._body = b"".join(chunks)
                        response = await call_next(request)
                else:
                    response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff", "Content-Security-Policy":
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})
        return response

    @app.exception_handler(RequestValidationError)
    async def sanitized_validation_error(request, error):
        # ValueError text may contain attacker input from URL parsing. Export
        # only field paths and fixed validation types, never input or context.
        return JSONResponse(status_code=422, content={"detail": [
            {"type": item["type"], "loc": item["loc"]} for item in error.errors()]})

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/setup", status_code=307)

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    def ready():
        return {"status": "ready"}

    @app.get("/setup", response_class=HTMLResponse, include_in_schema=False)
    def setup_page():
        page = SETUP_PAGE.read_text(encoding="utf-8")
        return HTMLResponse(page.replace("__READ_ONLY__", "true" if resolved_settings.read_only else "false"))

    @app.get("/api/v1/setup/status", response_model=SetupStatus, include_in_schema=False)
    def status(request: Request):
        runtime = request.app.state.setup_runtime
        return SetupStatus(state=runtime.state, setup_active=runtime.available and not resolved_settings.read_only,
                           role=runtime.role)

    @app.get("/api/v1/setup/prefill", response_model=SetupPrefill, include_in_schema=False)
    def prefill(request: Request):
        snapshot = request.app.state.setup_runtime.previous
        if not snapshot or not snapshot.role:
            return SetupPrefill()
        return SetupPrefill(**{key: getattr(snapshot, key) for key in
            ("locale", "device_name", "administrator_name", "role", "hub_endpoint", "network_mode", "network_interface")})

    @app.get("/api/v1/setup/capabilities", include_in_schema=False)
    def setup_capabilities(request: Request):
        runtime = request.app.state.setup_runtime
        interfaces = capabilities()
        return {"roles": ["node"] if install_profile is InstallProfile.NODE else ["standalone", "hub", "node"],
                "network_modes": ["preserve", "local"] + (["wifi"] if interfaces else []),
                "interfaces": interfaces, "recovery": runtime.recovery, "pending": runtime.pending,
                "complete": runtime.completed_attempt,
                "read_only": resolved_settings.read_only,
                "network_notice": "managed_wifi_available" if interfaces else "host_network_preserved"}

    @app.get("/api/v1/setup/networks", response_model=WifiNetworkList, include_in_schema=False)
    def networks():
        if not capabilities():
            return WifiNetworkList(items=[])
        cached = read_wifi_scan_cache(resolved_settings.data_dir)
        try:
            scanner = getattr(network, "scan_wifi_networks", None)
            items = merge_wifi_networks(cached, scanner()) if scanner else cached
        except Exception:
            items = cached
        return WifiNetworkList(items=[WifiNetworkOption(network_name=item.network_name,
            signal=item.signal, secured=item.secured) for item in items])

    @app.get("/api/v1/setup/theme", response_model=SetupTheme, include_in_schema=False)
    def theme():
        return _read_setup_theme(resolved_settings.core_database_path)

    @app.get("/api/v1/setup/diagnostics", include_in_schema=False)
    def diagnostics(request: Request):
        with request.app.state.setup_runtime.diagnostics.export() as chunks:
            return Response(content=b"".join(chunks), media_type="application/x-ndjson")

    @app.post("/api/v1/setup/configure", response_model=SetupOutcome, include_in_schema=False)
    def configure(configuration: SetupConfiguration, request: Request):
        runtime = request.app.state.setup_runtime
        try:
            validate_profile_role(install_profile, configuration.role)
        except RuntimeError:
            raise HTTPException(status_code=422, detail="role_requires_full_installation") from None
        if not runtime.lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="setup_busy")
        try:
            with runtime.journal.locked():
                runtime.apply(configuration, interfaces=capabilities())
                runtime.finish()
        except SetupFailure as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except NetworkAdapterError:
            raise HTTPException(status_code=503, detail="network_operation_failed") from None
        except (OSError, ProvisioningStoreError, NetworkRecoveryStoreError):
            raise HTTPException(status_code=503, detail="setup_persistence_failed") from None
        except ValueError:
            raise HTTPException(status_code=409, detail="administrator_setup_failed") from None
        finally:
            runtime.lock.release()
        return SetupOutcome(state=runtime.state, role=configuration.role, recovery_required=False,
                            enrollment=("preserved" if runtime.recovery else "awaiting_pairing")
                            if configuration.role.value == "node" else None)

    @app.post("/api/v1/setup/finish", include_in_schema=False)
    def finish(request: Request):
        runtime = request.app.state.setup_runtime
        if not runtime.lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="setup_busy")
        try:
            with runtime.journal.locked():
                runtime.finish()
        except SetupFailure as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Exception:
            raise HTTPException(status_code=503, detail="runtime_activation_failed") from None
        finally:
            runtime.lock.release()
        return {"status": "complete"}

    def captive_portal_redirect():
        return RedirectResponse("/setup", status_code=307)

    for path in ("/generate_204", "/hotspot-detect.html", "/connecttest.txt", "/ncsi.txt"):
        app.add_api_route(path, captive_portal_redirect, methods=["GET"], include_in_schema=False)
    return app


app = create_app()
